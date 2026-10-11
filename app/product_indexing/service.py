from app.database.connection import connection
from app.product_indexing.jobs import enqueue
from app.products.queries import list_products
import hashlib
from app.utils.nutrition import nutrition_summary
from app.utils.text import normalize_text


DOCUMENT_VERSION = "product-text-v2-nutrition"


def product_document(product):
    # Reviews are synthetic seed data, so they are excluded from retrieval evidence.
    lines = [
        "Name: " + normalize_text(product["name"]),
        "Category: " + normalize_text(product["category"]),
        "Description: " + normalize_text(product.get("description")),
    ]
    nutrition = nutrition_summary(product)
    if nutrition: lines.append(nutrition)
    return "\n".join(lines)


def document_hash(product):
    return hashlib.sha256((DOCUMENT_VERSION + "\n" + product_document(product)).encode()).hexdigest()


def schedule_all(database_path):
    with connection(database_path, write=True) as conn:
        products = list_products(conn)
        for product in products:
            enqueue(conn, product["product_id"], product["search_revision"])
        return len(products)


def reconcile(database_path, vectors):
    # Reading vectors before the SQL transaction avoids blocking writes during scroll.
    indexed = vectors.revisions()
    with connection(database_path, write=True) as conn:
        products = {p["product_id"]: p for p in list_products(conn)}
        queued = 0
        for product_id, product in products.items():
            payload = indexed.get(product_id, {})
            if (payload.get("revision") != product["search_revision"]
                or payload.get("document_hash") != document_hash(product)
                or payload.get("embedding_model") != vectors.model_name):
                enqueue(conn, product_id, product["search_revision"])
                queued += 1
        for product_id in indexed.keys() - products.keys():
            enqueue(conn, product_id, indexed[product_id].get("revision", 0), "delete")
            queued += 1
        return queued


