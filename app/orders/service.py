from app.utils.money import CURRENCY_CODE
from collections import Counter
from decimal import Decimal
from app.utils.errors import ServiceError
from app.database.connection import connection
from app.orders.queries import order_history


class OrderService:
    def __init__(self, database_path):
        self.database_path = database_path

    def create(self, payload, *, conn=None):
        if conn is None:
            with connection(self.database_path, write=True) as transaction:
                return self.create(payload, conn=transaction)
        if not payload.items:
            raise ServiceError(400, "Order must contain at least one item")
        quantities = Counter()
        for item in payload.items:
            if item.quantity <= 0:
                raise ServiceError(400, "Quantity must be positive")
            quantities[item.product_id] += item.quantity
        if not conn.execute("SELECT 1 FROM person WHERE person_id=?", (payload.person_id,)).fetchone():
            raise ServiceError(404, "Person not found")
        resolved, total = [], Decimal("0")
        for product_id, quantity in quantities.items():
            product = conn.execute("SELECT * FROM product WHERE product_id=?", (product_id,)).fetchone()
            if not product:
                raise ServiceError(404, f"Product {product_id} not found")
            if quantity > product["stock_quantity"]:
                raise ServiceError(400, f"Not enough stock for {product['name']}")
            price = Decimal(str(product["price"]))
            resolved.append((product_id,quantity,price))
            total += price*quantity
        status_id = conn.execute("SELECT status_id FROM order_status WHERE label='pending'").fetchone()[0]
        order_id = conn.execute("INSERT INTO orders(person_id,status_id,total_amount) VALUES(?,?,?)",
            (payload.person_id,status_id,str(total))).lastrowid
        for product_id,quantity,price in resolved:
            conn.execute("INSERT INTO order_items(order_id,product_id,quantity,unit_price) VALUES(?,?,?,?)", (order_id,product_id,quantity,str(price)))
            # The database trigger schedules vector metadata synchronization.
            conn.execute("UPDATE product SET stock_quantity=stock_quantity-? WHERE product_id=?", (quantity,product_id))
        return {"order_id": order_id, "total_amount": float(total), "currency": CURRENCY_CODE, "message": "Order created"}

    def history(self, person_id):
        with connection(self.database_path) as conn:
            return order_history(conn, person_id)
