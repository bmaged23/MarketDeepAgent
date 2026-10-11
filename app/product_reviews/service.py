from app.database.connection import connection
from app.product_reviews.schemas import ProductReview
from app.utils.errors import ServiceError


class ProductReviewService:
    def __init__(self, database_path):
        self.database_path = database_path

    def submit(self, person_id, payload):
        review = ProductReview.model_validate(payload)
        with connection(self.database_path, write=True) as conn:
            purchased = conn.execute("""SELECT s.label FROM orders o
                JOIN order_status s USING(status_id) JOIN order_items oi USING(order_id)
                WHERE o.person_id=? AND o.order_id=? AND oi.product_id=?""",
                (person_id, review.order_id, review.product_id)).fetchone()
            if not purchased:
                raise ServiceError(404, "Product not purchased in this customer's order")
            if purchased["label"] != "delivered":
                raise ServiceError(409, "Review is available after the order is delivered")
            conn.execute("""INSERT INTO verified_product_reviews(person_id,order_id,product_id,rating,comment)
                VALUES(?,?,?,?,?) ON CONFLICT(person_id,order_id,product_id) DO UPDATE SET
                rating=excluded.rating,comment=excluded.comment,updated_at=datetime('now')""",
                (person_id, review.order_id, review.product_id, review.rating, review.comment))
            return dict(conn.execute("""SELECT review_id,order_id,product_id,rating,comment,created_at,updated_at
                FROM verified_product_reviews WHERE person_id=? AND order_id=? AND product_id=?""",
                (person_id, review.order_id, review.product_id)).fetchone())

    def summary(self, product_id):
        with connection(self.database_path) as conn:
            row = conn.execute("""SELECT COUNT(*) AS review_count,COUNT(rating) AS rating_count,
                AVG(rating) AS average_rating FROM verified_product_reviews WHERE product_id=?""", (product_id,)).fetchone()
            return dict(row)
