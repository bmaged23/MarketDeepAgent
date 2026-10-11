"""Cart-agent evaluation using isolated SQL fixtures; never mutate the real cart."""
import argparse
from pathlib import Path
from app.config import get_settings, PROJECT_ROOT
from app.database.connection import connection
from app.agents.cart.agent import create_runner
from app.agents.cart.tools import CartTools
from app.model_clients.ollama import OllamaClient
from app.utils.agent_evaluation import (evaluation_catalog, ScriptedLLM, evidence, seed_order,
                                       stock, record_case, save_report, trace_cart, CART_METHODS, cart_scenario)
from app.utils.evaluation_trace import RecordedClient

CASES = ("view_empty", "add_products", "change_quantity", "remove_product", "clear_cart",
         "validate_stock", "prepare_checkout", "order_history", "order_status",
         "review_delivered", "review_before_delivery", "unresolved_product")



def evaluate_cases(settings, selected, offline=False):
    reports = []
    for case_id in selected:
        records = []
        try:
            with evaluation_catalog(settings) as (isolated, _, products):
                query, decision, context, validate = cart_scenario(isolated, products, case_id)
                llm = ScriptedLLM([decision]) if offline else OllamaClient(isolated)
                runner = trace_cart(create_runner(isolated, 1, llm), records)
                row = record_case(case_id, query, lambda: runner.run(query, evidence=context), validate, records)
                row["model_usage"] = getattr(llm, "usage", [])
                row["expected_decision"] = decision
                reports.append(row)
        except Exception as exc:
            reports.append({"case_id": case_id, "calls": records, "passed": False, "error_type": type(exc).__name__})
    return reports


def evaluate_tools(settings):
    with evaluation_catalog(settings) as (isolated, _, products):
        records = []
        tools = RecordedClient(CartTools(isolated, 1), records, CART_METHODS)
        p = products[0]
        initial = stock(isolated, p["product_id"])
        def workflow():
            tools.view_cart()
            tools.quote_cart([{"product_id": p["product_id"], "quantity": 1}])
            tools.update_cart([{"product_id": p["product_id"], "quantity": 1}])
            tools.validate_cart()
            tools.clear_cart()
            tools.update_cart([{"product_id": p["product_id"], "quantity": 1}])
            quote = tools.prepare_checkout()
            confirmation = {"token": quote["confirmation_token"], "confirmed": True,
                            "payment_method": "cash_on_delivery", "delivery_address": "Synthetic evaluation address"}
            receipt = tools.complete_order(confirmation)
            repeat = tools.complete_order(confirmation)
            order_id = receipt["order"]["order_id"]
            tools.order_history()
            tools.order_status(order_id)
            with connection(isolated.database_path, write=True) as conn:
                conn.execute("UPDATE orders SET status_id=(SELECT status_id FROM order_status WHERE label='delivered') WHERE order_id=?", (order_id,))
            review = tools.review_product(order_id, p["product_id"], 4, "Good product")
            return {"receipt": receipt, "repeat": repeat, "review": review}
        return [record_case("all_cart_tools", "Direct isolated tool workflow", workflow,
            lambda result: {"all_tools_called": CART_METHODS <= {r["operation"] for r in records},
                            "stock_deducted_once": stock(isolated,p["product_id"]) == initial - 1,
                            "checkout_idempotent": result["repeat"]["already_completed"],
                            "review_saved": result["review"]["rating"] == 4}, records)]


def main():
    parser = argparse.ArgumentParser(description="Test cart agent and every cart tool in isolated SQL; save a JSON report")
    parser.add_argument("--offline", action="store_true", help="Scripted model responses; no model quality claims")
    parser.add_argument("--max-cases", type=int, default=len(CASES))
    parser.add_argument("--case", choices=CASES)
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "data/evaluation_reports/cart_agent.json")
    args = parser.parse_args()
    if args.max_cases < 1: parser.error("--max-cases must be positive")
    report = {"agent": "cart", "mode": "offline_scripted" if args.offline else "live_ollama",
              "database_isolation": "Fresh temporary catalog copy and synthetic customers per case; no real order/customer data",
              "cases": []}
    try:
        settings = get_settings()
        report["tools"] = evaluate_tools(settings)
        report["cases"] = evaluate_cases(settings, [args.case] if args.case else CASES[:args.max_cases], args.offline)
    except Exception as exc:
        report["setup_error_type"] = type(exc).__name__
    return save_report(report, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
