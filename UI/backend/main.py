"""
SmartCart backend API.

Endpoints:
    GET  /api/categories        - list all categories
    GET  /api/products           - list products (optional ?category_id=, ?search=)
    GET  /api/products/{id}      - single product detail
    POST /api/register           - create a new person (writes to person table)
    POST /api/login               - verify email+password, returns person_id
    POST /api/orders              - create a real order (writes orders + order_items)
    GET  /api/orders/{person_id} - list a person's past orders

Run:
    /mnt/storage/abdelrahmanaamin/miniconda/envs/deep_agent_projects/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8600 --reload
"""

import hashlib
import secrets
import sqlite3
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr

DB_PATH = Path(__file__).parent.parent / "data" / "products.db"
FRONTEND_PATH = Path(__file__).parent.parent / "frontend"

app = FastAPI(title="SmartCart API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def hash_password(password: str, salt: Optional[str] = None) -> str:
    """Simple salted SHA-256 hash. Good enough for this project stage;
    swap for bcrypt/argon2 before handling real payment data."""
    if salt is None:
        salt = secrets.token_hex(16)
    digest = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    salt, _ = stored.split("$", 1)
    return hash_password(password, salt) == stored


class RegisterRequest(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    password: str
    phone: Optional[str] = None
    address: Optional[str] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class OrderItemRequest(BaseModel):
    product_id: int
    quantity: int


class OrderRequest(BaseModel):
    person_id: int
    items: List[OrderItemRequest]


@app.get("/api/categories")
def get_categories():
    conn = get_conn()
    rows = conn.execute("SELECT category_id, name FROM category ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/products")
def get_products(category_id: Optional[int] = None, search: Optional[str] = None):
    conn = get_conn()
    query = """
        SELECT p.product_id, p.name, p.description, p.price, p.stock_quantity,
               p.image_path, p.avg_rating, p.review, c.name AS category
        FROM product p
        JOIN category c ON p.category_id = c.category_id
        WHERE 1=1
    """
    params = []
    if category_id:
        query += " AND p.category_id = ?"
        params.append(category_id)
    if search:
        query += " AND (p.name LIKE ? OR p.description LIKE ?)"
        like_term = f"%{search}%"
        params.extend([like_term, like_term])
    query += " ORDER BY p.name"

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/products/{product_id}")
def get_product(product_id: int):
    conn = get_conn()
    row = conn.execute(
        """
        SELECT p.product_id, p.name, p.description, p.price, p.stock_quantity,
               p.image_path, p.avg_rating, p.review, c.name AS category
        FROM product p
        JOIN category c ON p.category_id = c.category_id
        WHERE p.product_id = ?
        """,
        (product_id,),
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Product not found")
    return dict(row)


@app.post("/api/register")
def register(payload: RegisterRequest):
    conn = get_conn()
    existing = conn.execute(
        "SELECT person_id FROM person WHERE email = ?", (payload.email,)
    ).fetchone()
    if existing:
        conn.close()
        raise HTTPException(status_code=400, detail="Email already registered")

    password_hash = hash_password(payload.password)
    cursor = conn.execute(
        """
        INSERT INTO person (first_name, last_name, email, phone, address, password_hash)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (payload.first_name, payload.last_name, payload.email, payload.phone, payload.address, password_hash),
    )
    conn.commit()
    person_id = cursor.lastrowid
    conn.close()
    return {"person_id": person_id, "first_name": payload.first_name, "message": "Registered successfully"}


@app.post("/api/login")
def login(payload: LoginRequest):
    conn = get_conn()
    row = conn.execute(
        "SELECT person_id, first_name, last_name, password_hash FROM person WHERE email = ?",
        (payload.email,),
    ).fetchone()
    conn.close()
    if not row or not row["password_hash"] or not verify_password(payload.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return {"person_id": row["person_id"], "first_name": row["first_name"], "last_name": row["last_name"]}


@app.post("/api/orders")
def create_order(payload: OrderRequest):
    if not payload.items:
        raise HTTPException(status_code=400, detail="Order must contain at least one item")

    conn = get_conn()

    person = conn.execute("SELECT person_id FROM person WHERE person_id = ?", (payload.person_id,)).fetchone()
    if not person:
        conn.close()
        raise HTTPException(status_code=404, detail="Person not found")

    pending_status = conn.execute("SELECT status_id FROM order_status WHERE label = 'pending'").fetchone()
    status_id = pending_status["status_id"] if pending_status else 1

    total_amount = 0.0
    resolved_items = []
    for item in payload.items:
        product = conn.execute(
            "SELECT product_id, name, price, stock_quantity FROM product WHERE product_id = ?",
            (item.product_id,),
        ).fetchone()
        if not product:
            conn.close()
            raise HTTPException(status_code=404, detail=f"Product {item.product_id} not found")
        if item.quantity <= 0:
            conn.close()
            raise HTTPException(status_code=400, detail="Quantity must be positive")
        if product["stock_quantity"] < item.quantity:
            conn.close()
            raise HTTPException(status_code=400, detail=f"Not enough stock for {product['name']}")

        line_total = product["price"] * item.quantity
        total_amount += line_total
        resolved_items.append((product["product_id"], item.quantity, product["price"]))

    cursor = conn.execute(
        "INSERT INTO orders (person_id, status_id, total_amount) VALUES (?, ?, ?)",
        (payload.person_id, status_id, round(total_amount, 2)),
    )
    order_id = cursor.lastrowid

    for product_id, quantity, unit_price in resolved_items:
        conn.execute(
            "INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES (?, ?, ?, ?)",
            (order_id, product_id, quantity, unit_price),
        )
        conn.execute(
            "UPDATE product SET stock_quantity = stock_quantity - ? WHERE product_id = ?",
            (quantity, product_id),
        )

    conn.commit()
    conn.close()
    return {"order_id": order_id, "total_amount": round(total_amount, 2), "message": "Order created"}


@app.get("/api/orders/{person_id}")
def get_orders(person_id: int):
    conn = get_conn()
    orders = conn.execute(
        """
        SELECT o.order_id, o.order_date, o.total_amount, s.label AS status
        FROM orders o
        JOIN order_status s ON o.status_id = s.status_id
        WHERE o.person_id = ?
        ORDER BY o.order_date DESC
        """,
        (person_id,),
    ).fetchall()

    result = []
    for order in orders:
        items = conn.execute(
            """
            SELECT oi.product_id, p.name, oi.quantity, oi.unit_price
            FROM order_items oi
            JOIN product p ON oi.product_id = p.product_id
            WHERE oi.order_id = ?
            """,
            (order["order_id"],),
        ).fetchall()
        result.append({**dict(order), "items": [dict(i) for i in items]})

    conn.close()
    return result


# Serve product images (they live in MarketDeepAgent/products/, a sibling of UI/)
PRODUCTS_IMAGES_PATH = Path(__file__).parent.parent.parent / "products"
if PRODUCTS_IMAGES_PATH.exists():
    app.mount("/products", StaticFiles(directory=str(PRODUCTS_IMAGES_PATH)), name="products")

# Serve the frontend (mounted LAST - it's a catch-all for "/")
app.mount("/", StaticFiles(directory=str(FRONTEND_PATH), html=True), name="frontend")
