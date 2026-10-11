from app.utils.money import CURRENCY_CODE
from decimal import Decimal
from app.database.connection import connection
from app.products.queries import get_product


class CartQuote:
    def __init__(self, database_path):
        self.database_path = database_path

    def quote_cart(self, items):
        """Quote from SQL. This tool does not place an order."""
        quantities = {}
        for item in items:
            quantity = item["quantity"]
            if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
                raise ValueError("Quantity must be a positive integer")
            product_id = item["product_id"]
            quantities[product_id] = quantities.get(product_id, 0) + quantity
        lines, total = [], Decimal("0")
        with connection(self.database_path) as conn:
            for product_id,quantity in quantities.items():
                product = get_product(conn, product_id)
                if not product or quantity > product["stock_quantity"]:
                    raise ValueError("Product unavailable or insufficient stock")
                subtotal = Decimal(str(product["price"]))*quantity
                lines.append({"product_id": product_id, "name": product["name"], "quantity": quantity, "subtotal": float(subtotal)})
                total += subtotal
        return {"items": lines, "total": float(total), "currency": CURRENCY_CODE, "requires_confirmation": True}
