from app.utils.money import CURRENCY_CODE

def order_history(conn, person_id):
    orders = conn.execute("""SELECT o.order_id,o.order_date,o.total_amount,s.label AS status
        FROM orders o JOIN order_status s ON o.status_id=s.status_id
        WHERE o.person_id=? ORDER BY o.order_date DESC,o.order_id DESC""", (person_id,)).fetchall()
    return [{**dict(order), "currency": CURRENCY_CODE, "items": [dict(item) for item in conn.execute("""
        SELECT oi.product_id,p.name,oi.quantity,oi.unit_price FROM order_items oi
        JOIN product p USING(product_id) WHERE oi.order_id=?""", (order["order_id"],))]} for order in orders]
