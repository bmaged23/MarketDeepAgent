def enqueue(conn, product_id, revision, operation="upsert"):
    conn.execute("""
        INSERT INTO product_index_jobs(product_id, revision, operation)
        VALUES (?, ?, ?)
        ON CONFLICT(product_id) DO UPDATE SET
          revision=excluded.revision, operation=excluded.operation,
          status='pending', attempts=0, error=NULL, next_attempt_at=0,
          updated_at=datetime('now')
    """, (product_id, revision, operation))


def status(conn, product_id):
    job = conn.execute("SELECT * FROM product_index_jobs WHERE product_id=?", (product_id,)).fetchone()
    return dict(job) if job else None
