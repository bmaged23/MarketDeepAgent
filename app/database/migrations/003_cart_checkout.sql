CREATE TABLE IF NOT EXISTS customer_cart (
    person_id INTEGER PRIMARY KEY REFERENCES person(person_id),
    revision INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS customer_cart_items (
    person_id INTEGER NOT NULL REFERENCES customer_cart(person_id),
    product_id INTEGER NOT NULL REFERENCES product(product_id),
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    PRIMARY KEY(person_id, product_id)
);
CREATE TABLE IF NOT EXISTS checkout_quotes (
    token TEXT PRIMARY KEY,
    person_id INTEGER NOT NULL REFERENCES person(person_id),
    cart_revision INTEGER NOT NULL,
    snapshot TEXT NOT NULL,
    expires_at INTEGER NOT NULL,
    order_id INTEGER UNIQUE REFERENCES orders(order_id)
);
CREATE TABLE IF NOT EXISTS order_checkout (
    order_id INTEGER PRIMARY KEY REFERENCES orders(order_id),
    payment_method TEXT NOT NULL,
    payment_status TEXT NOT NULL DEFAULT 'unpaid',
    delivery_address TEXT NOT NULL,
    shipping_status TEXT NOT NULL DEFAULT 'awaiting_fulfillment'
);
