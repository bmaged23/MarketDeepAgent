SELECT_PRODUCT = """
SELECT p.*, c.name AS category FROM product p
JOIN category c ON c.category_id=p.category_id
"""


def get_product(conn, product_id):
    row = conn.execute(SELECT_PRODUCT + " WHERE p.product_id=?", (product_id,)).fetchone()
    return dict(row) if row else None


def filter_clause(filters, alias="p"):
    clauses, params = [], []
    for field, operator, value in (
        ("category_id", "=", filters.category_id),
        ("price", ">=", filters.min_price),
        ("price", "<=", filters.max_price),
    ):
        if value is not None:
            clauses.append(f"{alias}.{field} {operator} ?")
            params.append(value)
    if filters.in_stock:
        clauses.append(f"{alias}.stock_quantity > 0")
    return (" AND ".join(clauses) or "1=1"), params


def list_products(conn, filters=None, search=None):
    clause, params = filter_clause(filters) if filters else ("1=1", [])
    if search:
        clause += " AND (p.name LIKE ? OR p.description LIKE ?)"
        params += [f"%{search}%", f"%{search}%"]
    return [dict(r) for r in conn.execute(SELECT_PRODUCT + " WHERE " + clause + " ORDER BY p.name", params)]
