-- SMARTCART FULL SCHEMA (v3 - complete)
-- Includes: category, product (already built) + person, order_status, orders, order_items (new)

-- ========== CATEGORY ==========
CREATE TABLE IF NOT EXISTS category (
    category_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE
);

-- ========== PRODUCT ==========
CREATE TABLE IF NOT EXISTS product (
    product_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    description     TEXT,
    price           DECIMAL(10, 2) NOT NULL CHECK (price >= 0),   -- EGP
    stock_quantity  INTEGER NOT NULL DEFAULT 0 CHECK (stock_quantity >= 0),
    category_id     INTEGER NOT NULL,
    image_prompt    TEXT,
    image_path      TEXT,
    avg_rating      DECIMAL(2,1) DEFAULT 0,     -- auto-calculated from review table
    rating_count    INTEGER DEFAULT 0,          -- auto-calculated from review table
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (category_id) REFERENCES category(category_id)
);

-- ========== PERSON (customers) ==========
CREATE TABLE IF NOT EXISTS person (
    person_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name  TEXT NOT NULL,
    last_name   TEXT NOT NULL,
    email       TEXT NOT NULL UNIQUE,
    phone       TEXT,
    address     TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

-- ========== ORDER_STATUS (lookup table, same idea as category) ==========
CREATE TABLE IF NOT EXISTS order_status (
    status_id INTEGER PRIMARY KEY AUTOINCREMENT,
    label     TEXT NOT NULL UNIQUE
);

-- ========== ORDERS ==========
CREATE TABLE IF NOT EXISTS orders (
    order_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id     INTEGER NOT NULL,
    status_id     INTEGER NOT NULL,
    order_date    TEXT DEFAULT (datetime('now')),
    total_amount  DECIMAL(10, 2) NOT NULL DEFAULT 0 CHECK (total_amount >= 0),
    created_at    TEXT DEFAULT (datetime('now')),
    updated_at    TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (person_id) REFERENCES person(person_id),
    FOREIGN KEY (status_id) REFERENCES order_status(status_id)
);

-- ========== ORDER_ITEMS (junction: order <-> product) ==========
CREATE TABLE IF NOT EXISTS order_items (
    order_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id      INTEGER NOT NULL,
    product_id    INTEGER NOT NULL,
    quantity      INTEGER NOT NULL CHECK (quantity > 0),
    unit_price    DECIMAL(10, 2) NOT NULL CHECK (unit_price >= 0),  -- price at time of order
    FOREIGN KEY (order_id) REFERENCES orders(order_id),
    FOREIGN KEY (product_id) REFERENCES product(product_id)
);

-- ========== REVIEW (person rates a product, comment optional) ==========
CREATE TABLE IF NOT EXISTS review (
    review_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id   INTEGER NOT NULL,
    product_id  INTEGER NOT NULL,
    rating      INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment     TEXT,                             -- optional text review
    created_at  TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (person_id) REFERENCES person(person_id),
    FOREIGN KEY (product_id) REFERENCES product(product_id),
    UNIQUE (person_id, product_id)                 -- one rating per person per product
);

-- Auto-update product.avg_rating / rating_count whenever a review changes
CREATE TRIGGER IF NOT EXISTS trg_review_insert
AFTER INSERT ON review
BEGIN
    UPDATE product
    SET avg_rating = (SELECT ROUND(AVG(rating), 1) FROM review WHERE product_id = NEW.product_id),
        rating_count = (SELECT COUNT(*) FROM review WHERE product_id = NEW.product_id)
    WHERE product_id = NEW.product_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_review_update
AFTER UPDATE ON review
BEGIN
    UPDATE product
    SET avg_rating = (SELECT ROUND(AVG(rating), 1) FROM review WHERE product_id = NEW.product_id),
        rating_count = (SELECT COUNT(*) FROM review WHERE product_id = NEW.product_id)
    WHERE product_id = NEW.product_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_review_delete
AFTER DELETE ON review
BEGIN
    UPDATE product
    SET avg_rating = (SELECT COALESCE(ROUND(AVG(rating), 1), 0) FROM review WHERE product_id = OLD.product_id),
        rating_count = (SELECT COUNT(*) FROM review WHERE product_id = OLD.product_id)
    WHERE product_id = OLD.product_id;
END;

-- ========== Auto-update updated_at on edit (SQLite trigger) ==========
CREATE TRIGGER IF NOT EXISTS trg_product_updated_at
AFTER UPDATE ON product
BEGIN
    UPDATE product SET updated_at = datetime('now') WHERE product_id = NEW.product_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_orders_updated_at
AFTER UPDATE ON orders
BEGIN
    UPDATE orders SET updated_at = datetime('now') WHERE order_id = NEW.order_id;
END;

-- ========== Seed the fixed lookup values ==========
INSERT OR IGNORE INTO order_status (label) VALUES
    ('pending'), ('confirmed'), ('shipped'), ('delivered'), ('cancelled');