"""Customer coordinator integration evaluation with isolated cart/order state."""
import argparse
from pathlib import Path
from app.config import get_settings, PROJECT_ROOT
from app.agents.cart.agent import create_runner as cart_runner
from app.agents.customer.agent import CustomerAgent
from app.agents.customer.tools import CustomerTools
from app.agents.retrieval.agent import create_runner as retrieval_runner, RetrievalAgent
from app.agents.retrieval.tools import RetrievalTools
from app.agents.retrieval.relevance import OllamaRelevanceJudge
from app.model_clients.ollama import OllamaClient
from app.model_clients.factory import embedding_client, vector_index
from app.product_search.service import create_search_service
from app.utils.agent_evaluation import (evaluation_catalog, ScriptedLLM, record_case,
                                       save_report, trace_cart, stock, cart_scenario)
from app.utils.evaluation_trace import RecordedClient

CASES = ("greeting", "product_lookup", "add_products", "view_cart", "prepare_checkout",
         "confirmed_checkout", "order_history", "order_status", "review_delivered", "review_before_delivery")


class FixtureSearch:
    """Deterministic offline candidates; SQL/product workflow still executes."""
    def __init__(self, products): self.products = products
    def search(self, query, filters, limit):
        return {"degraded": False, "results": [{"product": p, "score": 1, "sources": ["offline_fixture"]} for p in self.products[:limit]]}


def traced_retrieval(settings, products, records, offline, search):
    if offline:
        llm = ScriptedLLM([{"rewritten_query": " and ".join(p["name"] for p in products),
            "queries": [{"query": " and ".join(p["name"] for p in products)}]},
            {"approved_chunk_ids": [f"chunk_{i}" for i in range(min(len(products), settings.retrieval_results_per_query))]},
            {"retrieval_ok": True}])
        runner = RetrievalAgent(settings, RetrievalTools(settings.database_path, FixtureSearch(products)), llm,
                                OllamaRelevanceJudge(settings, llm))
    else:
        runner = retrieval_runner(settings, search)
    runner.llm = RecordedClient(runner.llm, records, {"chat"}, "retrieval")
    runner.judge.llm = runner.llm
    runner.judge = RecordedClient(runner.judge, records, {"grade"}, "retrieval")
    runner.tools = RecordedClient(runner.tools, records, {"categories", "search_products", "query_products", "product_details", "compare_products"}, "retrieval")
    return runner


def evaluate_cases(settings, selected, offline=False, embeddings=None, vectors=None):
    reports = []
    for case_id in selected:
        records = []
        try:
            with evaluation_catalog(settings) as (isolated, _, products):
                p = products[0]
                if case_id in {"greeting", "product_lookup"}:
                    query = "Hello!" if case_id == "greeting" else f"Find {p['name']} and tell me its price."
                    decision, validate_cart = {"action": "view_cart"}, None
                    steps = [] if case_id == "greeting" else ["retrieval"]
                else:
                    mapped = {"view_cart": "view_empty", "confirmed_checkout": "prepare_checkout"}.get(case_id, case_id)
                    query, decision, _, validate_cart = cart_scenario(isolated, products, mapped)
                    steps = ["retrieval", "cart"] if case_id == "add_products" else ["cart"]
                search = None if offline else create_search_service(isolated, embeddings, vectors)
                retrieval = traced_retrieval(isolated, products, records, offline, search)
                cart_llm = ScriptedLLM([decision, decision]) if offline else OllamaClient(isolated)
                cart = trace_cart(cart_runner(isolated, 1, cart_llm), records)
                llm = ScriptedLLM([{"steps": steps}, {"answer": "Offline scripted answer; inspect recorded tool state."}]) if offline else OllamaClient(isolated)
                customer = CustomerAgent(isolated,
                    RecordedClient(CustomerTools(retrieval, cart), records,
                                   {"retrieve_products", "manage_cart", "complete_confirmed_order"}, "customer"),
                    RecordedClient(llm, records, {"chat"}, "customer"))
                prior_stock = stock(isolated, p["product_id"])
                def run():
                    result = customer.run(query)
                    if case_id == "confirmed_checkout":
                        prepared = result["results"].get("cart", {})
                        prepared_checks = validate_cart(prepared)
                        token = prepared.get("output", {}).get("confirmation_token")
                        if not token:
                            return {"prepared": result, "prepared_checks": prepared_checks, "confirmation_missing": True}
                        confirmation = {"token": token, "confirmed": True, "payment_method": "cash_on_delivery",
                                        "delivery_address": "Synthetic evaluation address"}
                        return {"prepared": result, "prepared_checks": prepared_checks,
                                "confirmed": customer.confirm_order(confirmation), "repeat": customer.confirm_order(confirmation)}
                    return result
                def validate(result):
                    if case_id == "confirmed_checkout":
                        checks = dict(result["prepared_checks"])
                        if result.get("confirmation_missing"):
                            return {**checks, "confirmed_checkout": False}
                        receipt = result["confirmed"]["results"]["cart"]["output"]
                        checks.update(order_placed=receipt["order"]["status"] == "pending",
                                      payment_not_fabricated=receipt["order"]["payment_status"] == "unpaid",
                                      stock_deducted_once=stock(isolated,p["product_id"]) == prior_stock - 2,
                                      cart_cleared=not cart.tools.view_cart()["items"],
                                      repeat_idempotent=result["repeat"]["results"]["cart"]["output"]["already_completed"])
                        return checks
                    from app.agents.customer.schemas import CustomerReply
                    checks = {"answer_present": bool(result.get("answer", "").strip())}
                    try:
                        CustomerReply.model_validate({"answer": result.get("answer", "")})
                        checks["currency_is_usd"] = True
                    except ValueError:
                        checks["currency_is_usd"] = False
                    actual = result.get("results", {})
                    checks["correct_specialists"] = set(actual) == set(steps)
                    if case_id == "greeting": checks["no_cart_mutation"] = not cart.tools.view_cart()["items"]
                    elif case_id == "product_lookup":
                        retrieval_output = actual.get("retrieval", {})
                        names = {c["product"]["name"] for s in retrieval_output.get("sections", []) for c in s["chunks"]}
                        checks["requested_product_approved"] = p["name"] in names
                        checks["no_degraded_search"] = not retrieval_output.get("degraded", True)
                    elif "cart" in actual:
                        checks.update(validate_cart(actual["cart"]))
                    else: checks["cart_result_present"] = False
                    if case_id == "add_products":
                        calls = [r["operation"] for r in records]
                        checks["retrieval_before_cart_mutation"] = "retrieve_products" in calls and "update_cart" in calls and all(i > calls.index("retrieve_products") for i, operation in enumerate(calls) if operation == "update_cart")
                    checks["answer_model_excludes_checkout_token"] = all("confirmation_token" not in message["content"] for r in records if r["operation"] == "chat" and r.get("component") == "customer" for message in r["input"]["args"][0] if message["role"] == "user")
                    return checks
                row = record_case(case_id, query, run, validate, records)
                row["expected_specialists"] = steps
                row["expected_cart_decision"] = decision if "cart" in steps else None
                row["model_usage"] = {"customer": getattr(customer.llm, "usage", []),
                                      "cart": getattr(cart.llm, "usage", []),
                                      "retrieval": getattr(retrieval.llm, "usage", [])}
                reports.append(row)
        except Exception as exc:
            reports.append({"case_id": case_id, "calls": records, "passed": False, "error_type": type(exc).__name__})
    return reports


def main():
    parser = argparse.ArgumentParser(description="Test customer routing, retrieval/cart tools and confirmed checkout in isolated SQL")
    parser.add_argument("--offline", action="store_true", help="Scripted models/search; no live quality claims")
    parser.add_argument("--max-cases", type=int, default=len(CASES))
    parser.add_argument("--case", choices=CASES)
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "data/evaluation_reports/customer_agent.json")
    args = parser.parse_args()
    if args.max_cases < 1: parser.error("--max-cases must be positive")
    report = {"agent": "customer", "mode": "offline_scripted" if args.offline else "live_ollama_hybrid",
              "database_isolation": "Fresh temporary catalog copy and synthetic customers per case; live Qdrant is queried read-only",
              "limitations": "Routing and SQL state checks are automated; natural-language answer factuality needs human review. Offline success does not measure live model quality.", "cases": []}
    vectors = None
    try:
        settings = get_settings()
        embeddings = None if args.offline else embedding_client(settings)
        vectors = None if args.offline else vector_index(settings)
        report["cases"] = evaluate_cases(settings, [args.case] if args.case else CASES[:args.max_cases], args.offline, embeddings, vectors)
    except Exception as exc:
        report["setup_error_type"] = type(exc).__name__
    finally:
        if vectors is not None:
            try: vectors.close()
            except Exception as exc: report["setup_error_type"] = type(exc).__name__
    return save_report(report, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
