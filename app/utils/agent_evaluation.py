"""Shared isolated catalog fixtures and report handling for agent test commands."""
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from app.database.connection import connection, migrate
from app.products.queries import list_products
from app.agents.cart.tools import CartTools
from app.utils.evaluation_trace import RecordedClient

CART_METHODS = {"view_cart", "update_cart", "clear_cart", "validate_cart", "quote_cart",
                "prepare_checkout", "order_history", "order_status", "complete_order", "review_product"}


class ScriptedLLM:
    """Offline workflow testing only, not an evaluation of model quality."""
    def __init__(self, replies):
        self.replies = iter(replies)
        self.usage = []
    def chat(self, messages):
        return {"message": {"content": json.dumps(next(self.replies))}}


@contextmanager
def evaluation_catalog(settings):
    # Copy only catalog data, never real customers, orders, addresses or reviews.
    with connection(settings.database_path) as source:
        source.execute("BEGIN")
        categories = [tuple(r) for r in source.execute("SELECT category_id,name FROM category")]
        fields = "product_id,name,description,price,stock_quantity,category_id,image_path,calories_per_100,calorie_basis,calorie_status,calorie_source,calorie_notes"
        products = [tuple(r) for r in source.execute(f"SELECT {fields} FROM product")]
    with TemporaryDirectory(prefix="market-agent-evaluation-") as directory:
        path = Path(directory) / "evaluation.db"
        migrate(path)
        with connection(path, write=True) as conn:
            conn.executemany("INSERT INTO category(category_id,name) VALUES(?,?)", categories)
            conn.executemany(f"INSERT INTO product({fields}) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", products)
            conn.execute("INSERT INTO person(person_id,first_name,last_name,email) VALUES(1,'Evaluation','Customer','evaluation@example.test')")
            conn.execute("INSERT INTO person(person_id,first_name,last_name,email) VALUES(2,'Evaluation','Other','other@example.test')")
        isolated = settings.model_copy(update={"database_path": path})
        with connection(path) as conn:
            rows = list_products(conn)
        eligible = [p for p in rows if p["stock_quantity"] >= 3]
        if len(eligible) < 2:
            raise ValueError("Evaluation needs at least two catalog products with stock >= 3")
        yield isolated, rows, eligible[:2]


def evidence(products):
    return {"status": "done", "retrieval_ok": True, "degraded": False, "sections": [
        {"query": p["name"], "chunks": [{"approval": 1, "product": {k: p[k] for k in
         ("product_id", "name", "description", "price", "stock_quantity", "category", "category_id", "image_path", "calories_per_100", "calorie_basis", "calorie_status", "calorie_source", "calorie_notes")}}]}
        for p in products]}


def stock(settings, product_id):
    with connection(settings.database_path) as conn:
        return conn.execute("SELECT stock_quantity FROM product WHERE product_id=?", (product_id,)).fetchone()[0]


def seed_order(settings, delivered=False):
    with connection(settings.database_path) as conn:
        p = next(p for p in list_products(conn) if p["stock_quantity"] >= 3)
    tools = CartTools(settings, 1)
    tools.update_cart([{"product_id": p["product_id"], "quantity": 1}])
    quote = tools.prepare_checkout()
    receipt = tools.complete_order({"token": quote["confirmation_token"], "confirmed": True,
               "payment_method": "cash_on_delivery", "delivery_address": "Synthetic evaluation address"})
    order_id = receipt["order"]["order_id"]
    if delivered:
        with connection(settings.database_path, write=True) as conn:
            conn.execute("UPDATE orders SET status_id=(SELECT status_id FROM order_status WHERE label='delivered') WHERE order_id=?", (order_id,))
    return order_id, p


def record_case(case_id, query, run, validate, records):
    row = {"case_id": case_id, "query": query, "calls": records}
    started = perf_counter()
    try:
        result = run()
        checks = validate(result)
        row.update(output=result, checks=checks, passed=all(checks.values()))
    except Exception as exc:
        row.update(passed=False, error_type=type(exc).__name__)
        from app.utils.llm_json import StructuredResponseError
        if isinstance(exc, StructuredResponseError):
            # This exception contains sanitized schema locations/types only.
            row["validation_error"] = str(exc)
    row["duration_seconds"] = round(perf_counter() - started, 4)
    return row


def save_report(report, output):
    report["created_at"] = datetime.now(timezone.utc).isoformat()
    report["summary"] = {"cases": len(report.get("cases", [])),
                         "passed_cases": sum(c["passed"] for c in report.get("cases", []))}
    report["passed"] = bool(report.get("cases")) and all(c["passed"] for c in report["cases"]) and not report.get("setup_error_type")
    if "tools" in report:
        report["passed"] = report["passed"] and all(c["passed"] for c in report["tools"])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    failures = [{"case_id": c["case_id"], "error_type": c.get("error_type"),
                 "failed_checks": [k for k,v in c.get("checks", {}).items() if not v],
                 "failed_calls": [{k: call[k] for k in ("operation", "error_type", "http_status", "validation_errors") if k in call}
                                  for call in c["calls"] if call.get("status") == "error"]}
                for c in report.get("cases", []) + report.get("tools", []) if not c["passed"]]
    print(json.dumps({"passed": report["passed"], **report["summary"], "report": str(output),
                      "setup_error_type": report.get("setup_error_type"), "failures": failures}, indent=2))
    return 0 if report["passed"] else 1


def trace_cart(agent, records):
    agent.tools = RecordedClient(agent.tools, records, CART_METHODS, "cart")
    agent.llm = RecordedClient(agent.llm, records, {"chat"}, "cart")
    return agent


def cart_scenario(settings, products, case_id):
    p, other = products
    product_id = p["product_id"]
    tools = CartTools(settings, 1)
    order_id = None
    expected_items = []
    if case_id in {"change_quantity", "remove_product", "clear_cart", "validate_stock", "prepare_checkout"}:
        tools.update_cart([{"product_id": product_id, "quantity": 2}])
        expected_items = [(product_id, 2)]
    if case_id in {"order_history", "order_status", "review_delivered", "review_before_delivery"}:
        order_id, p = seed_order(settings, delivered=case_id == "review_delivered")
        product_id = p["product_id"]
    decision = {"action": "view_cart"}
    query = "Show my cart."
    if case_id == "add_products":
        query = f"Set my cart to include 2 {p['name']} (product {product_id}) and 1 {other['name']} (product {other['product_id']})."
        expected_items = [(product_id, 2), (other["product_id"], 1)]
        decision = {"action": "update_cart", "items": [{"product_id": i, "quantity": q} for i,q in expected_items]}
    elif case_id == "change_quantity":
        query = f"Change the quantity of product {product_id} to 3."
        expected_items = [(product_id, 3)]
        decision = {"action": "update_cart", "items": [{"product_id": product_id, "quantity": 3}]}
    elif case_id == "remove_product":
        query = f"Remove product {product_id} from my cart."
        expected_items = []
        decision = {"action": "update_cart", "items": [{"product_id": product_id, "quantity": 0}]}
    elif case_id == "clear_cart":
        query, decision, expected_items = "Clear my entire cart.", {"action": "clear_cart"}, []
    elif case_id == "validate_stock":
        with connection(settings.database_path, write=True) as conn:
            conn.execute("UPDATE product SET stock_quantity=1 WHERE product_id=?", (product_id,))
        query, decision = "Validate my cart against current stock.", {"action": "validate_cart"}
    elif case_id == "prepare_checkout":
        query, decision = "Prepare checkout for my cart; do not place an order yet.", {"action": "prepare_checkout"}
    elif case_id == "order_history":
        query, decision = "Show my previous orders.", {"action": "order_history"}
    elif case_id == "order_status":
        query, decision = f"Show the shipping and payment status of my order {order_id}.", {"action": "order_status", "order_id": order_id}
    elif case_id in {"review_delivered", "review_before_delivery"}:
        query = f"For product {product_id} in my order {order_id}, submit rating 4 and comment exactly 'Good product'."
        decision = {"action": "review_product", "order_id": order_id, "product_id": product_id, "rating": 4, "comment": "Good product"}
    elif case_id == "unresolved_product":
        query = "Add two of that product; no specific product has been identified yet."
        decision = {"action": "clarify", "clarification": "Which product do you want?"}
    before_stock = stock(settings, product_id)
    before_orders = len(tools.order_history())

    def validate(result):
        cart = tools.view_cart()
        checks = {"stock_not_deducted_by_cart_action": stock(settings, product_id) == before_stock,
                  "no_unconfirmed_orders": len(tools.order_history()) == before_orders,
                  "cart_quantities": sorted((i["product_id"],i["quantity"]) for i in cart["items"]) == sorted(expected_items)}
        if case_id == "unresolved_product":
            checks["asks_to_resolve_product"] = result["status"] in {"needs_clarification", "needs_retrieval"}
        elif case_id == "review_before_delivery":
            checks["blocks_early_review"] = result["status"] == "validation_failed" and not tools.order_status(order_id)["reviews"]
        else:
            checks["correct_action"] = result.get("action") == decision["action"] and result["status"] == "ok"
            output = result.get("output")
            if case_id == "validate_stock":
                checks["detects_insufficient_stock"] = isinstance(output, dict) and not output.get("valid", True)
            elif case_id == "prepare_checkout":
                checks["quote_requires_confirmation"] = isinstance(output, dict) and output.get("ready") is True and bool(output.get("confirmation_token")) and output.get("payment_status") == "unpaid"
            elif case_id == "order_history":
                checks["owned_history"] = isinstance(output, list) and len(output) == 1 and output[0]["order_id"] == order_id
            elif case_id == "order_status":
                checks["recorded_status"] = isinstance(output, dict) and output.get("order_id") == order_id and output.get("status") == "pending" and output.get("payment_status") == "unpaid"
            elif case_id == "review_delivered":
                saved = tools.order_status(order_id)["reviews"]
                checks["review_saved_exactly"] = saved == [{"product_id": product_id, "rating": 4, "comment": "Good product"}]
        return checks
    return query, decision, {} if case_id == "unresolved_product" else evidence(products), validate

