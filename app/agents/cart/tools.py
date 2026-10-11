from app.cart.service import CartService
from app.product_reviews.service import ProductReviewService
from app.cart.quotes import CartQuote


class CartTools:
    """Identity is bound by the caller; the model cannot choose another customer."""
    def __init__(self, settings, person_id):
        self.person_id = person_id
        self.service = CartService(settings.database_path, settings.cart_quote_ttl_seconds, settings.cart_max_items)
        self.quotes = CartQuote(settings.database_path)

    def view_cart(self):
        return self.service.view(self.person_id)

    def update_cart(self, items):
        """Set absolute quantities; quantity zero removes a product. Updates are atomic."""
        return self.service.update(self.person_id, items)

    def clear_cart(self):
        return self.service.clear(self.person_id)

    def validate_cart(self):
        return self.view_cart()

    def quote_cart(self, items):
        return self.quotes.quote_cart(items)

    def prepare_checkout(self):
        return self.service.prepare_checkout(self.person_id)

    def order_history(self):
        return self.service.history(self.person_id)

    def order_status(self, order_id):
        return self.service.order(self.person_id, order_id)

    def complete_order(self, confirmation):
        """Trusted caller only; never offered as an LLM-selectable tool."""
        return self.service.checkout(self.person_id, confirmation)


    def review_product(self, order_id, product_id, rating=None, comment=""):
        return ProductReviewService(self.service.database_path).submit(self.person_id,
            {"order_id": order_id, "product_id": product_id, "rating": rating, "comment": comment})
