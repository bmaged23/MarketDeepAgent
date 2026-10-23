from app.database.connection import connection
from app.products.queries import get_product
from app.products.catalog_query import CatalogQuery, query_catalog, project_product
from app.product_search.schemas import SearchFilters
from app.utils.text import normalize_text
import re


class RetrievalTools:
    def __init__(self, database_path, search_service):
        self.database_path = database_path
        self.search_service = search_service

    def categories(self):
        with connection(self.database_path) as conn:
            return [dict(row) for row in conn.execute("SELECT category_id, name FROM category ORDER BY category_id")]

    def resolve_named_products(self, query):
        """Resolve full catalog names from request text, never guessed IDs or gold labels."""
        text = normalize_text(query).casefold()
        with connection(self.database_path) as conn:
            products = [dict(row) for row in conn.execute("SELECT product_id,name FROM product")]
        matches = []
        for product in products:
            name = normalize_text(product['name']).casefold()
            for match in re.finditer(r'(?<!\w)' + re.escape(name) + r'(?!\w)', text):
                matches.append((match.start(), match.end(), product))
        # Prefer the longest literal name when one SKU name contains another.
        chosen = []
        for start, end, product in sorted(matches, key=lambda row: -(row[1]-row[0])):
            if (not any(start < b and end > a for a,b,_ in chosen)
                or any(start == a and end == b for a,b,_ in chosen)):
                chosen.append((start,end,product))
        result = {}
        for _,_,product in sorted(chosen,key=lambda row:(row[0],row[1],row[2]['product_id'])):
            result[product['product_id']] = product
        return list(result.values())

    def search_products(self, query, category_id=None, min_price=None, max_price=None, in_stock=False, limit=None):
        filters = SearchFilters(category_id=category_id, min_price=min_price, max_price=max_price, in_stock=in_stock)
        return self.search_service.search(query, filters, limit)

    def query_products(self, catalog=None, filters=None, max_results=100):
        return query_catalog(self.database_path, catalog or CatalogQuery(), filters, max_results)

    def product_details(self, product_id):
        with connection(self.database_path) as conn:
            product = get_product(conn, product_id)
        if not product:
            raise ValueError("Product not found")
        return project_product(product)

    def compare_products(self, product_ids):
        if not 2 <= len(product_ids) <= 10 or len(set(product_ids)) < 2:
            raise ValueError("Compare between two and ten products")
        return [self.product_details(product_id) for product_id in dict.fromkeys(product_ids)]
