from app.products.queries import filter_clause
from app.utils.text import keyword_query


class BM25Index:
    def search(self, conn, query, filters, limit):
        match = keyword_query(query)
        if not match:
            return []
        clause, params = filter_clause(filters)
        rows = conn.execute("""
            SELECT p.product_id, bm25(product_fts, 5.0, 2.0, 1.0, 1.0) AS score
            FROM product_fts JOIN product p ON p.product_id=product_fts.rowid
            WHERE product_fts MATCH ? AND """ + clause + """
            ORDER BY score ASC, p.product_id ASC LIMIT ?
        """, [match, *params, limit])
        return [(row["product_id"], row["score"]) for row in rows]
