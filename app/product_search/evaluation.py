import argparse
import json
import math
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from app.database.connection import connection, migrate
from app.products.queries import list_products
from app.product_search.schemas import SearchFilters
from app.utils.logging import configure_logging


def retrieval_metrics(retrieved_ids, relevant_ids, k):
    relevant = set(relevant_ids)
    top = retrieved_ids[:k]
    hits = len(set(top) & relevant)
    first = next((rank for rank,product_id in enumerate(top,1) if product_id in relevant),None)
    seen = set()
    dcg = 0.0
    for rank, product_id in enumerate(top, 1):
        if product_id in relevant and product_id not in seen:
            dcg += 1 / math.log2(rank + 1)
        seen.add(product_id)
    ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(k, len(relevant)) + 1))
    return {"recall_at_k": hits/len(relevant) if relevant else 0.0,
            "precision_at_k": hits/k,
            "reciprocal_rank": 1/first if first else 0.0,
            "ndcg_at_k": dcg/ideal if ideal else 0.0}


def evaluate(search_service, cases, product_ids_by_name, modes, limit):
    reports = {}
    for mode in modes:
        metrics, degraded, details = [], 0, []
        for case in cases:
            relevant = [product_ids_by_name[name] for name in case["relevant_product_names"]]
            result = search_service.search(case["query"], SearchFilters(**case.get("filters",{})), limit, mode)
            degraded += int(result["degraded"])
            row = retrieval_metrics([r["product"]["product_id"] for r in result["results"]],relevant,limit)
            metrics.append(row)
            details.append({"case_id": case.get("case_id"), "query": case["query"],
                            "query_type": case.get("query_type", "unspecified"),
                            "expected_products": case["relevant_product_names"],
                            "degraded": result["degraded"], "metrics": row,
                            "results": [{"name": r["product"]["name"], "score": r["score"],
                                         "sources": r["sources"]} for r in result["results"]]})
        reports[mode] = {"queries":len(cases), "degraded_queries":degraded,
            **{key:sum(row[key] for row in metrics)/len(metrics) for key in metrics[0]},
            "per_query": details}
    return reports


def compare_weights(service, cases, product_ids_by_name, limit, weights=None):
    """Evaluate a 10-percentage-point grid; never recommend degraded retrieval."""
    original = service.fusion_method, service.bm25_weight, service.vector_weight
    weights = [i / 10 for i in range(11)] if weights is None else list(weights)
    if not weights or any(not math.isfinite(w) or not 0 <= w <= 1 for w in weights):
        raise ValueError("BM25 weights must be a nonempty list of values between 0 and 1")
    try:
        baselines = evaluate(service, cases, product_ids_by_name, ["bm25", "vector"], limit)
        if not any(row["results"] for row in baselines["vector"]["per_query"]):
            raise RuntimeError("Vector baseline returned no candidates; verify collection, model, and indexing before tuning")
        service.fusion_method = "weighted_sum"
        rows = []
        for weight in dict.fromkeys(weights):
            service.bm25_weight = weight
            service.vector_weight = 1 - weight
            metrics = evaluate(service, cases, product_ids_by_name, ["hybrid"], limit)["hybrid"]
            rows.append({"bm25_weight": service.bm25_weight,
                         "vector_weight": service.vector_weight, **metrics})
        degraded = any(row["degraded_queries"] for row in rows)
        best_score = max(row["ndcg_at_k"] for row in rows)
        best = [row for row in rows if abs(row["ndcg_at_k"] - best_score) < 1e-10]
        return {"limit": limit, "selection_metric": "ndcg_at_k", "baselines": baselines,
                "weights": rows, "valid": not degraded,
                "best_weights": [] if degraded else best,
                "note": "Provisional on these labels; validate on independent shopping queries. "
                        "Endpoint weights use hybrid candidate unions, so consult the pure baselines too."}
    finally:
        service.fusion_method, service.bm25_weight, service.vector_weight = original


def main():
    from app.config import get_settings, PROJECT_ROOT
    from app.model_clients.factory import embedding_client,vector_index
    from app.product_search.service import create_search_service
    parser = argparse.ArgumentParser(description="Compare retrieval against a small labeled catalog query set")
    parser.add_argument("--cases", type=Path, default=PROJECT_ROOT/"data/search_evaluation.json")
    parser.add_argument("--modes", nargs="+", choices=["bm25","vector","hybrid"], default=["bm25","vector","hybrid"])
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--sweep", action="store_true", help="Compare BM25/vector weights from 0/100 to 100/0")
    parser.add_argument("--output", type=Path, help="Report path; defaults to data/evaluation_reports/retrieval_vanila.json")
    parser.add_argument("--weights", nargs="+", type=float,
                        help="BM25 fractions for --sweep, e.g. 0.3 0.5 0.7; vector = 1 - BM25")
    parser.add_argument("--split", choices=["all", "tune", "test"], default="all",
                        help="Tune on tune cases; confirm the chosen weight on held-out test cases")
    parser.add_argument("--bm25-weight", type=float, help="Override BM25 weight for this run; vector = 1 - BM25")
    args=parser.parse_args()
    if args.weights is not None and (not args.sweep or
            any(not math.isfinite(w) or not 0 <= w <= 1 for w in args.weights)):
        parser.error("--weights requires --sweep and values between 0 and 1")
    created_at = datetime.now(timezone.utc)
    if args.output is None:
        args.output = PROJECT_ROOT / "data/evaluation_reports/retrieval_vanila.json"
    configure_logging()
    settings=get_settings()
    if not 1 <= args.limit <= settings.search_max_limit:
        parser.error("--limit is outside the configured search range")
    cases=json.loads(args.cases.read_text())
    if args.split != "all":
        cases = [case for case in cases if case.get("split") == args.split]
    if not cases:
        parser.error("Evaluation cases must not be empty")
    if args.bm25_weight is not None:
        if not math.isfinite(args.bm25_weight) or not 0 <= args.bm25_weight <= 1:
            parser.error("--bm25-weight must be between 0 and 1")
        settings = settings.model_copy(update={"bm25_weight": args.bm25_weight,
            "vector_weight": 1 - args.bm25_weight, "search_fusion_method": "weighted_sum"})
    migrate(settings.database_path)
    with connection(settings.database_path) as conn:
        by_name={p["name"]:p["product_id"] for p in list_products(conn)}
    missing={name for case in cases for name in case["relevant_product_names"] if name not in by_name}
    if missing:
        parser.error("Missing labeled catalog products: "+", ".join(sorted(missing)))
    vectors=vector_index(settings)
    try:
        embeddings = embedding_client(settings)
        # Reuse each query vector across baselines and weights within this run.
        embeddings.encode_query = lru_cache(maxsize=len(cases))(embeddings.encode_query)
        service=create_search_service(settings,embeddings,vectors)
        report = (compare_weights(service,cases,by_name,args.limit,args.weights) if args.sweep else
                  evaluate(service,cases,by_name,args.modes,args.limit))
        report["run"] = {"created_at": created_at.isoformat(),
                         "dataset": str(args.cases), "split": args.split, "limit": args.limit,
                         "embedding_model": settings.embedding_model,
                         "collection": settings.qdrant_collection,
                         "fusion_method": "weighted_sum" if args.sweep else service.fusion_method,
                         "bm25_weight": service.bm25_weight, "vector_weight": service.vector_weight,
                         "bm25_candidates": service.bm25_candidates,
                         "vector_candidates": service.vector_candidates}
        output = json.dumps(report, indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(output + "\n")
            if args.sweep:
                summary = {"run": report["run"], "valid": report["valid"],
                    "selection_metric": report["selection_metric"],
                    "baselines": {mode: {k:v for k,v in row.items() if k != "per_query"}
                                  for mode,row in report["baselines"].items()},
                    "weights": [{k:v for k,v in row.items() if k != "per_query"} for row in report["weights"]],
                    "best_weights": [{k:v for k,v in row.items() if k != "per_query"} for row in report["best_weights"]]}
            else:
                summary = {mode: {k:v for k,v in report[mode].items() if k != "per_query"}
                           for mode in args.modes}
                summary["run"] = report["run"]
            print(json.dumps(summary, indent=2))
            print(f"Detailed report: {args.output}")
        else:
            print(output)
        if args.sweep and not report["valid"]:
            raise SystemExit("Weight comparison invalid: vector retrieval degraded; fix it and rerun.")
        if not args.sweep and any(report[mode]["degraded_queries"] for mode in args.modes):
            raise SystemExit("Evaluation contains degraded retrieval; fix vector search before comparing modes.")
    finally:
        vectors.close()


if __name__ == "__main__":
    main()
