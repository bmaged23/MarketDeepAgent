from pathlib import Path
from app.database.connection import connection
from app.products.queries import get_product
from app.product_indexing.jobs import status


class ProductNotFound(ValueError):
    pass


class InvalidProduct(ValueError):
    pass


class ProductService:
    def __init__(self, database_path, project_root):
        self.database_path, self.project_root = database_path, Path(project_root)

    def _validate(self, conn, data):
        allowed = {"name", "description", "price", "stock_quantity", "category_id", "image_path", "calories_per_100", "calorie_basis", "calorie_status", "calorie_source", "calorie_notes"}
        if set(data) - allowed:
            raise InvalidProduct("Unsupported product fields")
        if "category_id" in data and not conn.execute("SELECT 1 FROM category WHERE category_id=?", (data["category_id"],)).fetchone():
            raise InvalidProduct("Category does not exist")
        image = data.get("image_path")
        if image:
            images_root = (self.project_root / "products/images").resolve()
            image_file = (self.project_root / image.lstrip("/")).resolve()
            if not image_file.is_relative_to(images_root) or not image_file.is_file():
                raise InvalidProduct("Image must reference an existing file under products/images")

    def create(self, data):
        with connection(self.database_path, write=True) as conn:
            self._validate(conn, data)
            fields = list(data)
            cursor = conn.execute("INSERT INTO product (" + ",".join(fields) + ") VALUES (" + ",".join("?" for _ in fields) + ")", [data[f] for f in fields])
            product = get_product(conn, cursor.lastrowid)
            return {"product": product, "indexing": status(conn, cursor.lastrowid)}

    def update(self, product_id, data):
        with connection(self.database_path, write=True) as conn:
            if not get_product(conn, product_id):
                raise ProductNotFound("Product not found")
            self._validate(conn, data)
            if data:
                conn.execute("UPDATE product SET " + ",".join(f"{field}=?" for field in data) + " WHERE product_id=?", [*data.values(), product_id])
            return {"product": get_product(conn, product_id), "indexing": status(conn, product_id)}

    def delete(self, product_id):
        with connection(self.database_path, write=True) as conn:
            if not get_product(conn, product_id):
                raise ProductNotFound("Product not found")
            if conn.execute("SELECT 1 FROM order_items WHERE product_id=?", (product_id,)).fetchone():
                raise InvalidProduct("Product has order history and cannot be deleted; set stock to zero instead")
            conn.execute("DELETE FROM product WHERE product_id=?", (product_id,))
            return {"product_id": product_id, "indexing": status(conn, product_id)}
