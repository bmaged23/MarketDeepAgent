from app.utils.money import CURRENCY_CODE
import json
import secrets
import time
from decimal import Decimal
from app.cart.schemas import CartChange, CheckoutConfirmation
from app.database.connection import connection
from app.orders.service import OrderService
from app.orders.schemas import OrderRequest
from app.orders.queries import order_history
from app.utils.errors import ServiceError


class CartService:
    """Customer-scoped persistent cart; quoted checkout is atomic and idempotent."""
    def __init__(self, database_path, quote_ttl_seconds=900, max_items=100):
        self.database_path = database_path
        self.quote_ttl_seconds, self.max_items = quote_ttl_seconds, max_items

    @staticmethod
    def _customer(conn, person_id):
        if type(person_id) is not int or person_id <= 0:
            raise ValueError("Customer ID must be a positive integer")
        if not conn.execute("SELECT 1 FROM person WHERE person_id=?", (person_id,)).fetchone():
            raise ServiceError(404, "Customer not found")

    def _view(self, conn, person_id):
        self._customer(conn, person_id)
        cart = conn.execute("SELECT revision FROM customer_cart WHERE person_id=?", (person_id,)).fetchone()
        rows = conn.execute("""SELECT p.product_id,p.name,p.price,p.stock_quantity,ci.quantity
            FROM customer_cart_items ci JOIN product p USING(product_id)
            WHERE ci.person_id=? ORDER BY p.product_id""", (person_id,)).fetchall()
        lines, total, issues = [], Decimal("0"), []
        for row in rows:
            line = dict(row)
            subtotal = Decimal(str(row["price"])) * row["quantity"]
            line["subtotal"] = float(subtotal)
            total += subtotal
            if row["quantity"] > row["stock_quantity"]:
                issues.append({"product_id": row["product_id"], "reason": "insufficient_stock"})
            lines.append(line)
        if not lines:
            issues.append({"reason": "empty_cart"})
        return {"person_id": person_id, "revision": cart["revision"] if cart else 0,
                "items": lines, "total": float(total), "currency": CURRENCY_CODE,
                "valid": not issues, "issues": issues}

    def view(self, person_id):
        with connection(self.database_path) as conn:
            return self._view(conn, person_id)

    def update(self, person_id, items, expected_revision=None):
        changes = [CartChange.model_validate(item) for item in items]
        if not changes or len(changes) > self.max_items:
            raise ValueError("Supply between one and the configured maximum cart changes")
        if len({c.product_id for c in changes}) != len(changes):
            raise ValueError("Each product may appear only once in an update")
        with connection(self.database_path, write=True) as conn:
            self._customer(conn, person_id)
            conn.execute("INSERT OR IGNORE INTO customer_cart(person_id) VALUES(?)", (person_id,))
            if expected_revision is not None and self._view(conn, person_id)['revision'] != expected_revision:
                raise ServiceError(409, "Your cart changed; refresh it before updating")
            for item in changes:
                if item.quantity == 0:
                    conn.execute("DELETE FROM customer_cart_items WHERE person_id=? AND product_id=?", (person_id, item.product_id))
                    continue
                p = conn.execute("SELECT stock_quantity FROM product WHERE product_id=?", (item.product_id,)).fetchone()
                if not p or item.quantity > p["stock_quantity"]:
                    raise ServiceError(409, "Product unavailable or insufficient stock")
                conn.execute("""INSERT INTO customer_cart_items VALUES(?,?,?)
                    ON CONFLICT(person_id,product_id) DO UPDATE SET quantity=excluded.quantity""",
                    (person_id, item.product_id, item.quantity))
            count = conn.execute("SELECT COUNT(*) FROM customer_cart_items WHERE person_id=?", (person_id,)).fetchone()[0]
            if count > self.max_items:
                raise ServiceError(400, "Cart exceeds maximum distinct items")
            conn.execute("UPDATE customer_cart SET revision=revision+1,updated_at=datetime('now') WHERE person_id=?", (person_id,))
            return self._view(conn, person_id)

    def clear(self, person_id):
        with connection(self.database_path, write=True) as conn:
            self._customer(conn, person_id)
            conn.execute("DELETE FROM customer_cart_items WHERE person_id=?", (person_id,))
            conn.execute("UPDATE customer_cart SET revision=revision+1,updated_at=datetime('now') WHERE person_id=?", (person_id,))
            return self._view(conn, person_id)

    @staticmethod
    def _snapshot(cart):
        return json.dumps({"revision": cart["revision"], "items": [
            {k: p[k] for k in ("product_id", "quantity", "price")} for p in cart["items"]]}, sort_keys=True)

    def prepare_checkout(self, person_id):
        with connection(self.database_path, write=True) as conn:
            cart = self._view(conn, person_id)
            if not cart["valid"]:
                return {"ready": False, "cart": cart, "next_step": "resolve_cart_issues"}
            token, expires = secrets.token_urlsafe(32), int(time.time()) + self.quote_ttl_seconds
            conn.execute("INSERT INTO checkout_quotes(token,person_id,cart_revision,snapshot,expires_at) VALUES(?,?,?,?,?)",
                         (token, person_id, cart["revision"], self._snapshot(cart), expires))
            return {"ready": True, "cart": cart, "confirmation_token": token, "expires_at": expires,
                    "next_step": "confirm_order_and_delivery_address", "payment_status": "unpaid",
                    "supported_payment_methods": ["cash_on_delivery"]}

    def checkout(self, person_id, confirmation):
        confirmation = CheckoutConfirmation.model_validate(confirmation)
        if not confirmation.confirmed:
            raise ServiceError(400, "Explicit customer confirmation is required")
        with connection(self.database_path, write=True) as conn:
            self._customer(conn, person_id)
            quote = conn.execute("SELECT * FROM checkout_quotes WHERE token=? AND person_id=?", (confirmation.token, person_id)).fetchone()
            if not quote:
                raise ServiceError(404, "Checkout quote not found")
            if quote["order_id"] is not None:
                return {"order": self._order(conn, person_id, quote["order_id"]), "already_completed": True}
            cart = self._view(conn, person_id)
            if quote["expires_at"] <= int(time.time()) or not cart["valid"] or quote["snapshot"] != self._snapshot(cart):
                raise ServiceError(409, "Cart, price, stock or quote validity changed; prepare checkout again")
            payload = OrderRequest(person_id=person_id, items=[{"product_id": p["product_id"], "quantity": p["quantity"]} for p in cart["items"]])
            order = OrderService(self.database_path).create(payload, conn=conn)
            conn.execute("INSERT INTO order_checkout(order_id,payment_method,delivery_address) VALUES(?,?,?)",
                         (order["order_id"], confirmation.payment_method, confirmation.delivery_address))
            conn.execute("UPDATE checkout_quotes SET order_id=? WHERE token=?", (order["order_id"], confirmation.token))
            conn.execute("DELETE FROM customer_cart_items WHERE person_id=?", (person_id,))
            conn.execute("UPDATE customer_cart SET revision=revision+1,updated_at=datetime('now') WHERE person_id=?", (person_id,))
            return {"order": self._order(conn, person_id, order["order_id"]), "already_completed": False}

    def _order(self, conn, person_id, order_id):
        orders = [o for o in order_history(conn, person_id) if o["order_id"] == order_id]
        if not orders:
            raise ServiceError(404, "Order not found for this customer")
        extra = conn.execute("SELECT payment_method,payment_status,delivery_address,shipping_status FROM order_checkout WHERE order_id=?", (order_id,)).fetchone()
        metadata = dict(extra) if extra else {"payment_status": "unknown", "shipping_status": orders[0]["status"]}
        if orders[0]["status"] in {"shipped", "delivered", "cancelled"}:
            metadata["shipping_status"] = orders[0]["status"]
        reviews = [dict(r) for r in conn.execute("SELECT product_id,rating,comment FROM verified_product_reviews WHERE person_id=? AND order_id=?", (person_id, order_id))]
        return {**orders[0], **metadata, "reviews": reviews,
                "review_eligible": orders[0]["status"] == "delivered",
                "tracking_number": None, "tracking_available": False}

    def history(self, person_id):
        with connection(self.database_path) as conn:
            self._customer(conn, person_id)
            return [self._order(conn, person_id, o["order_id"]) for o in order_history(conn, person_id)]

    def order(self, person_id, order_id):
        if type(order_id) is not int or order_id <= 0:
            raise ValueError("Order ID must be a positive integer")
        with connection(self.database_path) as conn:
            self._customer(conn, person_id)
            return self._order(conn, person_id, order_id)
