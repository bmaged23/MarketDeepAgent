"""
FINAL clean build (v2): creates category + product tables from schema.sql,
inserts the 6 categories, then inserts all 30 products already linked to the
correct category_id. Uses the same image_prompt style you approved, and the
same image_path values matching your renamed Gemini images.

Run on the H100 (delete the old products.db first):
    rm products.db
    /mnt/storage/abdelrahmanaamin/miniconda/envs/deep_agent_projects/bin/python seed_products_v2.py
"""

import sqlite3
import re
from pathlib import Path

DB_PATH = Path(__file__).parent / "products.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

IMAGE_PROMPT_TEMPLATE = (
    "Professional advertisement-style product photography of {name}, placed on "
    "an elegant wooden table, warm natural lighting, soft background blur, "
    "{props}, shallow depth of field, high-end commercial photography, "
    "photorealistic, 4k quality, no text or watermark."
)

PROPS_BY_NAME = {
    "Lipton Yellow Label Tea": "with a steaming cup of tea and loose tea leaves scattered beside it",
    "Twinings English Breakfast Tea": "with a steaming cup of tea and a small silver tea strainer beside it",
    "Nescafe Gold Coffee": "with a cup of hot coffee and a few coffee beans scattered beside it",
    "Lavazza Espresso Coffee": "with a small espresso cup and coffee beans scattered beside it",
    "Green Tea Matcha": "with a bowl of matcha and a bamboo whisk beside it",
    "Orange Juice 1L": "with a glass of orange juice and a few orange slices beside it",
    "Sparkling Water": "with a chilled glass of sparkling water and ice cubes beside it",
    "Whole Milk 1L": "with a glass of milk beside it",
    "Greek Yogurt": "with a small bowl of yogurt and a spoon beside it",
    "Cheddar Cheese Block": "with a wooden cheese board and a cheese knife beside it",
    "Butter 250g": "with a few butter curls on a small plate beside it",
    "White Sandwich Bread": "with a few bread slices and a cutting board beside it",
    "Croissants Pack of 4": "with a basket lined with cloth and one croissant broken open beside it",
    "Whole Wheat Bread": "with a few bread slices and grains scattered on the table beside it",
    "Chocolate Muffins": "with one muffin broken open showing chocolate chips beside it",
    "Potato Chips Salted": "with a small bowl of chips spilled beside it",
    "Mixed Nuts 500g": "with a small wooden bowl of mixed nuts beside it",
    "Chocolate Bar": "with a few broken chocolate pieces beside it",
    "Popcorn Microwave": "with a small bowl of popcorn beside it",
    "Biscuits Digestive": "with a couple of biscuits stacked beside it, one with a bite taken",
    "Basmati Rice 5kg": "with a small bowl of cooked rice beside it",
    "Spaghetti Pasta": "with a plate of cooked spaghetti twirled with a fork beside it",
    "Olive Oil 1L": "with a small glass dish for dipping oil and a sprig of rosemary beside it",
    "Sugar 1kg": "with a small wooden spoon and a few sugar cubes beside it",
    "Salt 500g": "with a small dish of salt and a wooden spoon beside it",
    "Fresh Bananas 1kg": "with a wooden bowl of bananas beside it",
    "Tomatoes 1kg": "with a wooden bowl of fresh tomatoes beside it",
    "Onions 1kg": "with a woven basket of onions beside it",
    "Apples 1kg": "with a wooden bowl of fresh apples beside it",
    "Cucumbers 1kg": "with sliced cucumber rounds on a small plate beside it",
}


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


# (name, description, price_egp, stock_quantity, category_name)
PRODUCTS = [
    ("Lipton Yellow Label Tea", "Classic black tea bags, 100 count box", 85.00, 120, "Beverages"),
    ("Twinings English Breakfast Tea", "Premium black tea bags, 50 count box", 250.00, 80, "Beverages"),
    ("Nescafe Gold Coffee", "Instant coffee jar, 200g", 220.00, 100, "Beverages"),
    ("Lavazza Espresso Coffee", "Ground espresso coffee, 250g bag", 450.00, 60, "Beverages"),
    ("Green Tea Matcha", "Matcha green tea bags, 25 count box", 180.00, 70, "Beverages"),
    ("Orange Juice 1L", "100% pure orange juice, chilled carton", 45.00, 90, "Beverages"),
    ("Sparkling Water", "Carbonated mineral water, 1L bottle", 20.00, 150, "Beverages"),
    ("Whole Milk 1L", "Fresh whole milk, pasteurized carton", 35.00, 130, "Dairy"),
    ("Greek Yogurt", "Creamy strained yogurt, 500g tub", 60.00, 100, "Dairy"),
    ("Cheddar Cheese Block", "Aged cheddar cheese, 250g block", 150.00, 70, "Dairy"),
    ("Butter 250g", "Salted butter block, 250g", 90.00, 80, "Dairy"),
    ("White Sandwich Bread", "Sliced white bread loaf, 600g", 25.00, 100, "Bakery"),
    ("Croissants Pack of 4", "Buttery French croissants, pack of 4", 55.00, 60, "Bakery"),
    ("Whole Wheat Bread", "Sliced whole wheat bread loaf, 600g", 30.00, 90, "Bakery"),
    ("Chocolate Muffins", "Chocolate chip muffins, pack of 6", 65.00, 50, "Bakery"),
    ("Potato Chips Salted", "Crispy salted potato chips, 150g bag", 35.00, 140, "Snacks"),
    ("Mixed Nuts 500g", "Assorted roasted nuts, 500g pack", 180.00, 60, "Snacks"),
    ("Chocolate Bar", "Milk chocolate bar, 100g", 40.00, 160, "Snacks"),
    ("Popcorn Microwave", "Butter flavored microwave popcorn, 3 pack", 50.00, 90, "Snacks"),
    ("Biscuits Digestive", "Whole wheat digestive biscuits, 400g pack", 45.00, 100, "Snacks"),
    ("Basmati Rice 5kg", "Premium long grain basmati rice, 5kg bag", 350.00, 70, "Grains & Staples"),
    ("Spaghetti Pasta", "Durum wheat spaghetti pasta, 500g pack", 40.00, 120, "Grains & Staples"),
    ("Olive Oil 1L", "Extra virgin olive oil, 1L bottle", 280.00, 50, "Grains & Staples"),
    ("Sugar 1kg", "Refined white sugar, 1kg bag", 30.00, 150, "Grains & Staples"),
    ("Salt 500g", "Iodized table salt, 500g pack", 10.00, 160, "Grains & Staples"),
    ("Fresh Bananas 1kg", "Ripe fresh bananas, 1kg", 35.00, 100, "Fruits & Vegetables"),
    ("Tomatoes 1kg", "Fresh red tomatoes, 1kg", 25.00, 110, "Fruits & Vegetables"),
    ("Onions 1kg", "Fresh yellow onions, 1kg", 20.00, 120, "Fruits & Vegetables"),
    ("Apples 1kg", "Fresh red apples, 1kg", 60.00, 100, "Fruits & Vegetables"),
    ("Cucumbers 1kg", "Fresh cucumbers, 1kg", 20.00, 110, "Fruits & Vegetables"),
]

CATEGORIES = [
    "Beverages", "Dairy", "Bakery", "Snacks", "Grains & Staples", "Fruits & Vegetables"
]


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA_PATH.read_text())

    # Insert categories first
    for cat_name in CATEGORIES:
        conn.execute("INSERT OR IGNORE INTO category (name) VALUES (?);", (cat_name,))
    conn.commit()

    category_lookup = dict(conn.execute("SELECT name, category_id FROM category;").fetchall())

    # Insert products, already linked to the right category_id
    rows = []
    for name, desc, price, stock, category_name in PRODUCTS:
        props = PROPS_BY_NAME.get(name, "styled with a complementary prop beside it")
        image_prompt = IMAGE_PROMPT_TEMPLATE.format(name=name, props=props)
        image_path = f"products/images/{slugify(name)}.png"
        category_id = category_lookup[category_name]
        rows.append((name, desc, price, stock, category_id, image_prompt, image_path))

    conn.executemany(
        """
        INSERT INTO product
            (name, description, price, stock_quantity, category_id, image_prompt, image_path)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()

    count = conn.execute("SELECT COUNT(*) FROM product").fetchone()[0]
    print(f"Inserted {count} products, linked to {len(CATEGORIES)} categories, in {DB_PATH}")
    conn.close()


if __name__ == "__main__":
    main()