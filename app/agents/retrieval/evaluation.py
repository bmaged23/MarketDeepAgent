"""Persist test traces only; normal RetrievalAgent execution never writes files."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from app.agents.retrieval.agent import create_runner
from app.agents.retrieval.tools import RetrievalTools
from app.config import get_settings
from app.database.connection import connection
from app.model_clients.factory import embedding_client, vector_index
from app.product_search.service import create_search_service
from app.products.queries import list_products


from app.utils.evaluation_trace import RecordedClient


def check(name, call, validate, expected_error=False):
    started = perf_counter()
    try:
        output = call()
        passed = False if expected_error else bool(validate(output))
        return {"name": name, "passed": passed, "output": output,
                "duration_seconds": round(perf_counter() - started, 4)}
    except Exception as exc:
        return {"name": name, "passed": expected_error and isinstance(exc, ValueError),
                "error_type": type(exc).__name__,
                "duration_seconds": round(perf_counter() - started, 4)}


def evaluate_tools(tools, products, case, limit):
    records = []
    traced = RecordedClient(tools, records, {"categories", "product_details", "compare_products", "search_products"})
    ids = [p["product_id"] for p in products[:2]]
    expected = products[0]
    filters = case.get("filters", {})

    def search_valid(output):
        if output["degraded"] or len(output["results"]) > limit:
            return False
        by_id = {p["product_id"]: p for p in products}
        for row in output["results"]:
            p = row["product"]
            if p["product_id"] not in by_id or not row["sources"]:
                return False
            if any(p[k] != by_id[p["product_id"]][k] for k in ("name", "price", "stock_quantity")):
                return False
            if filters.get("category_id") is not None and p["category_id"] != filters["category_id"]:
                return False
            if filters.get("min_price") is not None and p["price"] < filters["min_price"]:
                return False
            if filters.get("max_price") is not None and p["price"] > filters["max_price"]:
                return False
            if filters.get("in_stock") and p["stock_quantity"] <= 0:
                return False
        return bool(output["results"])

    checks = [
        check("categories", lambda: traced.categories(), lambda rows: bool(rows) and all(r["category_id"] > 0 and r["name"] for r in rows)),
        check("product_details", lambda: traced.product_details(ids[0]), lambda p: all(p[k] == expected[k] for k in p)),
        check("compare_products", lambda: traced.compare_products(ids), lambda rows: [p["product_id"] for p in rows] == ids),
        check("search_products", lambda: traced.search_products(case["query"], **filters, limit=limit), search_valid),
        check("missing_product", lambda: traced.product_details(max(p["product_id"] for p in products) + 1), None, True),
        check("comparison_requires_distinct_products", lambda: traced.compare_products([ids[0], ids[0]]), None, True),
        check("invalid_price_range", lambda: traced.search_products("tea", min_price=100, max_price=1), None, True),
    ]
    return {"checks": checks, "calls": records, "passed": all(c["passed"] for c in checks)}


def evaluate_agent(runner_factory, cases, products):
    reports = []
    by_id = {p["product_id"]: p for p in products}
    for case in cases:
        records = []
        row = {"case_id": case["case_id"], "query": case.get("agent_expectations", {}).get("user_message", case["query"]),
               "expected_products": case["relevant_product_names"], "calls": records}
        started = perf_counter()
        try:
            runner = runner_factory()
            runner.tools = RecordedClient(runner.tools, records, {"categories", "search_products", "product_details", "compare_products"})
            runner.llm = RecordedClient(runner.llm, records, {"chat"})
            if hasattr(runner.judge, "llm"):
                runner.judge.llm = runner.llm
            runner.judge = RecordedClient(runner.judge, records, {"grade"})
            result = runner.run(row["query"])
            chunks = [c for s in result["sections"] for c in s["chunks"]]
            names = {c["product"]["name"] for c in chunks}
            factual = all(c["product"]["product_id"] in by_id and all(
                value == by_id[c["product"]["product_id"]].get(key)
                for key, value in c["product"].items()) for c in chunks)
            expected_filters = case.get("agent_expectations", {}).get("expected_filters", case.get("filters", {}))
            search_calls = [c for c in records if c["operation"] == "search_products"]
            filters_preserved = bool(search_calls) and all(
                all(c["input"]["kwargs"].get(k) == v for k, v in expected_filters.items())
                for c in search_calls)
            checks = {"filters_preserved": filters_preserved, "retrieval_complete": result["retrieval_ok"],
                      "expected_products_found": set(row["expected_products"]) <= names,
                      "approved_only": all(c["approval"] == 1 for c in chunks),
                      "facts_match_sql": factual,
                      "no_degraded_search": not result["degraded"],
                      "search_budget": result["searches"] <= runner.settings.retrieval_max_searches,
                      "query_headings": all("Query: " + s["query"] in result["context"] for s in result["sections"])}
            row.update(output=result, checks=checks, passed=all(checks.values()))
        except Exception as exc:
            row.update(passed=False, error_type=type(exc).__name__)
        row["duration_seconds"] = round(perf_counter() - started, 4)
        reports.append(row)
    return reports


def main():
    root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description="Test retrieval tools and agent; save inputs/outputs in a JSON report")
    parser.add_argument("--dataset", type=Path, default=root / "evaluation/datasets/search-starter-v1.json")
    parser.add_argument("--output", type=Path, default=root / "data/evaluation_reports/retrieval_agent.json")
    parser.add_argument("--split", choices=["all", "tune", "test"], default="all")
    parser.add_argument("--max-cases", type=int, default=3, help="Default 3; use 48 for the entire starter dataset")
    parser.add_argument("--tools-only", action="store_true", help="Skip cloud model calls; search still needs Qdrant and embeddings")
    args = parser.parse_args()
    if args.max_cases < 1:
        parser.error("--max-cases must be positive")
    cases = json.loads(args.dataset.read_text())
    cases = [c for c in cases if args.split == "all" or c["split"] == args.split][:args.max_cases]
    if not cases:
        parser.error("No selected dataset cases")
    settings = get_settings()
    report = {"created_at": datetime.now(timezone.utc).isoformat(), "dataset": str(args.dataset),
              "split": args.split, "selected_cases": len(cases), "tools_only": args.tools_only,
              "configuration": {"bm25_weight": settings.bm25_weight, "vector_weight": settings.vector_weight},
              "limitations": "Starter positive labels are not exhaustive. Extra approved products require human relevance review."}
    vectors = None
    try:
        with connection(settings.database_path) as conn:
            products = list_products(conn)
        if len(products) < 2:
            raise ValueError("Tool evaluation requires at least two SQL products")
        vectors = vector_index(settings)
        search = create_search_service(settings, embedding_client(settings), vectors)
        report["tools"] = evaluate_tools(RetrievalTools(settings.database_path, search), products, cases[0], settings.retrieval_results_per_query)
        report["agent_cases"] = [] if args.tools_only else evaluate_agent(lambda: create_runner(settings, search), cases, products)
        report["passed"] = report["tools"]["passed"] and all(r["passed"] for r in report["agent_cases"])
    except Exception as exc:
        report.update(passed=False, setup_error_type=type(exc).__name__)
    finally:
        if vectors is not None:
            try:
                vectors.close()
            except Exception as exc:
                report.update(passed=False, cleanup_error_type=type(exc).__name__)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    failures = []
    for case in report.get("agent_cases", []):
        for call in case["calls"]:
            if call.get("status") == "error":
                failures.append({"case_id": case["case_id"], **{k: call[k] for k in ("operation", "error_type", "http_status", "endpoint_path", "validation_errors") if k in call}})
        if not case["passed"] and not any(f["case_id"] == case["case_id"] for f in failures):
            failures.append({"case_id": case["case_id"], "error_type": case.get("error_type"), "failed_checks": [k for k, v in case.get("checks", {}).items() if not v]})
    print(json.dumps({"passed": report["passed"], "selected_cases": len(cases), "report": str(args.output), "failures": failures, "setup_error_type": report.get("setup_error_type"), "failed_tool_checks": [c["name"] for c in report.get("tools", {}).get("checks", []) if not c["passed"]]}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
