CREATE TABLE IF NOT EXISTS verified_product_reviews (
    review_id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL REFERENCES person(person_id),
    order_id INTEGER NOT NULL REFERENCES orders(order_id),
    product_id INTEGER NOT NULL REFERENCES product(product_id),
    rating INTEGER CHECK(rating BETWEEN 1 AND 5),
    comment TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(person_id,order_id,product_id),
    CHECK(rating IS NOT NULL OR length(trim(comment)) > 0)
);
