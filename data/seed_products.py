"""Seed the sample catalog without duplicating existing product names.

Run from the project root: python data/seed_products.py
Existing products and customer/order records are preserved.
"""

import sqlite3
import re
import random
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import PROJECT_ROOT
from app.database.connection import migrate
from app.products.nutrition import apply_catalog_nutrition

DB_PATH = Path(__file__).parent / "products.db"

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

    # ===== props for the 70 new products =====
    "Ottoman Turkish Coffee": "with a small brass coffee pot and a tiny cup beside it",
    "Hibiscus Tea Karkade": "with a glass of ruby red hibiscus tea beside it",
    "Mango Juice 1L": "with a glass of mango juice and mango slices beside it",
    "Apple Juice 1L": "with a glass of apple juice and apple slices beside it",
    "Frost Iced Tea Peach": "with a chilled glass of iced tea and peach slices beside it",
    "Volt Energy Drink": "with condensation droplets and ice cubes beside it",
    "Chamomile Tea": "with a cup of chamomile tea and dried chamomile flowers beside it",
    "Mineral Water 1.5L": "with a glass of water and ice cubes beside it",
    "Feta Cheese 250g": "with cubed feta on a small plate with olives beside it",
    "Cream Cheese 200g": "with cream cheese spread on a cracker beside it",
    "Labneh 500g": "with a drizzle of olive oil over labneh in a small bowl beside it",
    "Rayeb Fermented Milk 500ml": "with a glass of rayeb beside it",
    "Golden Slice Cheese": "with a cheese slice unwrapped beside it",
    "Whipping Cream 250ml": "with a dollop of whipped cream on a spoon beside it",
    "Condensed Milk 400g": "with condensed milk drizzled on a small plate beside it",
    "Cheddar Slices": "with a stack of cheddar slices beside it",
    "Greek Yogurt Drink": "with a glass poured from the bottle beside it",
    "Baladi Bread 5pcs": "with a woven bread basket beside it",
    "Pita Bread 6pcs": "with one pita torn open beside it",
    "Toast Bread": "with two toasted slices on a small plate beside it",
    "Sugar Ring Donuts": "with a donut with a bite taken beside it",
    "Chocolate Cake Slice": "with a fork and cake crumbs beside it",
    "Butter Cookies": "with a few cookies stacked beside it",
    "Bosco Rusk": "with a rusk dipped in a cup of tea beside it",
    "Croissant Single": "with a croissant broken open showing flaky layers beside it",
    "Sesame Bread Sticks": "with breadsticks standing in a small glass beside it",
    "Sweet Popcorn": "with popcorn spilled from a small bowl beside it",
    "Twist Pretzels": "with a small bowl of pretzels beside it",
    "Corn Chips": "with a small bowl of corn chips beside it",
    "Tahini Halawa 250g": "with a slice of halawa on a small plate beside it",
    "Turkish Delight": "with dusted powdered sugar pieces beside it",
    "Dried Fruits Mix": "with a wooden bowl of mixed dried fruits beside it",
    "PowerBite Granola Bars": "with one granola bar broken in half beside it",
    "Lentils 1kg": "with a small bowl of cooked lentil soup beside it",
    "Fava Beans Foul 1kg": "with a bowl of cooked foul medames beside it",
    "Vermicelli 400g": "with toasted vermicelli in a small pan beside it",
    "Couscous 500g": "with a bowl of fluffy cooked couscous beside it",
    "Corn Oil 1L": "with a small glass cruet of oil beside it",
    "White Vinegar 500ml": "with a small glass dish for dipping beside it",
    "Black Pepper 100g": "with a pepper grinder beside it",
    "Ground Cumin 100g": "with a small wooden spoon of cumin beside it",
    "All-Purpose Flour 1kg": "with a light dusting of flour and a wooden spoon beside it",
    "Split Peas 1kg": "with a small bowl of cooked split peas beside it",
    "Chickpeas 1kg": "with a small bowl of cooked chickpeas beside it",
    "Cocoa Powder 200g": "with a dusting of cocoa powder and a whisk beside it",
    "Golden Meadow Honey": "with a honey dipper drizzling honey beside it",
    "Tahini 400g": "with a swirl of tahini in a small bowl beside it",
    "Oranges 1kg": "with a halved orange showing juicy segments beside it",
    "Strawberries 500g": "with a few strawberries scattered beside it",
    "Grapes 1kg": "with a small bunch of grapes beside it",
    "Watermelon Whole": "with a watermelon slice cut open beside it",
    "Mango 1kg": "with a sliced mango showing its golden flesh beside it",
    "Lemon 1kg": "with a halved lemon beside it",
    "Garlic 250g": "with a few garlic cloves peeled beside it",
    "Potatoes 1kg": "with a few potatoes in a rustic basket beside it",
    "Carrots 1kg": "with a bunch of carrots with green tops beside it",
    "Zucchini 1kg": "with sliced zucchini rounds beside it",
    "Eggplant 1kg": "with a halved eggplant beside it",
    "Bell Pepper 1kg": "with sliced bell pepper rings in different colors beside it",
    "Baby Spinach 500g": "with fresh spinach leaves scattered beside it",
    "Lettuce Head": "with a few loose lettuce leaves beside it",
    "Peach 1kg": "with a halved peach showing the pit beside it",
    "Pear 1kg": "with a sliced pear beside it",
    "Guava 1kg": "with a halved guava showing pink flesh beside it",
    "Pomegranate 1kg": "with pomegranate seeds scattered beside it",
    "Green Peas 500g": "with a pea pod opened beside it",
    "Green Beans 500g": "with a bundle of green beans tied together beside it",
    "Cauliflower Head": "with a cauliflower floret broken off beside it",
    "Cabbage Head": "with a cabbage leaf peeled back beside it",
    "Molokhia Frozen 400g": "with a bowl of cooked molokhia soup beside it",
}


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


# (name, description, price_egp, stock_quantity, category_name)
PRODUCTS = [
    ("Lipton Yellow Label Tea", "Classic black tea bags, 100 count box", 5.49, 120, "Beverages"),
    ("Twinings English Breakfast Tea", "Premium black tea bags, 50 count box", 5.99, 80, "Beverages"),
    ("Nescafe Gold Coffee", "Instant coffee jar, 200g", 9.99, 100, "Beverages"),
    ("Lavazza Espresso Coffee", "Ground espresso coffee, 250g bag", 7.99, 60, "Beverages"),
    ("Green Tea Matcha", "Matcha green tea bags, 25 count box", 5.49, 70, "Beverages"),
    ("Orange Juice 1L", "100% pure orange juice, chilled carton", 2.49, 90, "Beverages"),
    ("Sparkling Water", "Carbonated mineral water, 1L bottle", 1.29, 150, "Beverages"),
    ("Whole Milk 1L", "Fresh whole milk, pasteurized carton", 1.49, 130, "Dairy"),
    ("Greek Yogurt", "Creamy strained yogurt, 500g tub", 3.49, 100, "Dairy"),
    ("Cheddar Cheese Block", "Aged cheddar cheese, 250g block", 3.99, 70, "Dairy"),
    ("Butter 250g", "Salted butter block, 250g", 3.49, 80, "Dairy"),
    ("White Sandwich Bread", "Sliced white bread loaf, 600g", 2.49, 100, "Bakery"),
    ("Croissants Pack of 4", "Buttery French croissants, pack of 4", 4.99, 60, "Bakery"),
    ("Whole Wheat Bread", "Sliced whole wheat bread loaf, 600g", 3.49, 90, "Bakery"),
    ("Chocolate Muffins", "Chocolate chip muffins, pack of 6", 5.49, 50, "Bakery"),
    ("Potato Chips Salted", "Crispy salted potato chips, 150g bag", 2.49, 140, "Snacks"),
    ("Mixed Nuts 500g", "Assorted roasted nuts, 500g pack", 8.99, 60, "Snacks"),
    ("Chocolate Bar", "Milk chocolate bar, 100g", 1.99, 160, "Snacks"),
    ("Popcorn Microwave", "Butter flavored microwave popcorn, 3 pack", 3.49, 90, "Snacks"),
    ("Biscuits Digestive", "Whole wheat digestive biscuits, 400g pack", 3.49, 100, "Snacks"),
    ("Basmati Rice 5kg", "Premium long grain basmati rice, 5kg bag", 16.99, 70, "Grains & Staples"),
    ("Spaghetti Pasta", "Durum wheat spaghetti pasta, 500g pack", 1.79, 120, "Grains & Staples"),
    ("Olive Oil 1L", "Extra virgin olive oil, 1L bottle", 11.99, 50, "Grains & Staples"),
    ("Sugar 1kg", "Refined white sugar, 1kg bag", 1.99, 150, "Grains & Staples"),
    ("Salt 500g", "Iodized table salt, 500g pack", 0.99, 160, "Grains & Staples"),
    ("Fresh Bananas 1kg", "Ripe fresh bananas, 1kg", 1.49, 100, "Fruits & Vegetables"),
    ("Tomatoes 1kg", "Fresh red tomatoes, 1kg", 2.49, 110, "Fruits & Vegetables"),
    ("Onions 1kg", "Fresh yellow onions, 1kg", 1.79, 120, "Fruits & Vegetables"),
    ("Apples 1kg", "Fresh red apples, 1kg", 3.99, 100, "Fruits & Vegetables"),
    ("Cucumbers 1kg", "Fresh cucumbers, 1kg", 1.99, 110, "Fruits & Vegetables"),

    # ===== 70 new products (batch 2) =====
    ("Ottoman Turkish Coffee", "Finely ground Turkish coffee, 200g tin", 6.49, 50, "Beverages"),
    ("Hibiscus Tea Karkade", "Dried hibiscus flowers for traditional karkade tea, 200g", 4.99, 70, "Beverages"),
    ("Mango Juice 1L", "100% pure mango nectar, chilled carton", 2.99, 80, "Beverages"),
    ("Apple Juice 1L", "100% pure apple juice, chilled carton", 2.29, 80, "Beverages"),
    ("Frost Iced Tea Peach", "Peach flavored iced tea, 500ml bottle", 1.49, 100, "Beverages"),
    ("Volt Energy Drink", "Carbonated energy drink, 250ml can", 1.99, 120, "Beverages"),
    ("Chamomile Tea", "Soothing chamomile tea bags, 20 count box", 3.49, 60, "Beverages"),
    ("Mineral Water 1.5L", "Natural mineral water, 1.5L bottle", 0.99, 200, "Beverages"),
    ("Feta Cheese 250g", "Traditional brined feta cheese, 250g", 4.49, 60, "Dairy"),
    ("Cream Cheese 200g", "Smooth spreadable cream cheese, 200g tub", 2.49, 70, "Dairy"),
    ("Labneh 500g", "Strained yogurt cheese, 500g tub", 4.99, 65, "Dairy"),
    ("Rayeb Fermented Milk 500ml", "Traditional fermented milk drink, 500ml", 1.99, 90, "Dairy"),
    ("Golden Slice Cheese", "Processed cheese slices, 200g pack", 2.49, 90, "Dairy"),
    ("Whipping Cream 250ml", "Dairy whipping cream, 250ml carton", 2.49, 55, "Dairy"),
    ("Condensed Milk 400g", "Sweetened condensed milk, 400g can", 2.49, 80, "Dairy"),
    ("Cheddar Slices", "Aged cheddar cheese slices, 200g pack", 2.99, 75, "Dairy"),
    ("Greek Yogurt Drink", "Drinkable Greek yogurt, 250ml bottle", 1.79, 85, "Dairy"),
    ("Baladi Bread 5pcs", "Traditional Egyptian flatbread, pack of 5", 1.99, 150, "Bakery"),
    ("Pita Bread 6pcs", "Soft pita bread pockets, pack of 6", 2.49, 130, "Bakery"),
    ("Toast Bread", "Sliced toast bread loaf, 500g", 2.29, 100, "Bakery"),
    ("Sugar Ring Donuts", "Glazed sugar ring donuts, pack of 4", 4.99, 50, "Bakery"),
    ("Chocolate Cake Slice", "Rich chocolate cake slice", 2.99, 40, "Bakery"),
    ("Butter Cookies", "Classic butter cookies, 300g box", 3.49, 90, "Bakery"),
    ("Bosco Rusk", "Crunchy sweet rusk toast, 300g pack", 2.49, 100, "Bakery"),
    ("Croissant Single", "Single buttery croissant", 1.49, 80, "Bakery"),
    ("Sesame Bread Sticks", "Crunchy sesame breadsticks, 150g pack", 1.99, 90, "Bakery"),
    ("Sweet Popcorn", "Sweet flavored popcorn, 100g bag", 1.99, 110, "Snacks"),
    ("Twist Pretzels", "Salted twist pretzels, 150g bag", 2.49, 100, "Snacks"),
    ("Corn Chips", "Crunchy corn chips, 150g bag", 2.29, 110, "Snacks"),
    ("Tahini Halawa 250g", "Traditional tahini sweet halva, 250g", 3.49, 60, "Snacks"),
    ("Turkish Delight", "Assorted Turkish delight, 300g box", 4.49, 55, "Snacks"),
    ("Dried Fruits Mix", "Assorted dried fruits, 300g pack", 5.99, 45, "Snacks"),
    ("PowerBite Granola Bars", "Oats and honey granola bars, pack of 5", 3.99, 70, "Snacks"),
    ("Lentils 1kg", "Red lentils, 1kg bag", 3.49, 90, "Grains & Staples"),
    ("Fava Beans Foul 1kg", "Dried fava beans for foul medames, 1kg", 2.99, 90, "Grains & Staples"),
    ("Vermicelli 400g", "Thin pasta vermicelli, 400g pack", 1.49, 100, "Grains & Staples"),
    ("Couscous 500g", "Fine couscous grains, 500g pack", 2.49, 70, "Grains & Staples"),
    ("Corn Oil 1L", "Pure corn cooking oil, 1L bottle", 3.99, 60, "Grains & Staples"),
    ("White Vinegar 500ml", "Distilled white vinegar, 500ml bottle", 1.29, 100, "Grains & Staples"),
    ("Black Pepper 100g", "Ground black pepper, 100g jar", 2.99, 80, "Grains & Staples"),
    ("Ground Cumin 100g", "Ground cumin spice, 100g jar", 2.49, 80, "Grains & Staples"),
    ("All-Purpose Flour 1kg", "Refined wheat flour, 1kg bag", 1.49, 120, "Grains & Staples"),
    ("Split Peas 1kg", "Yellow split peas, 1kg bag", 2.79, 70, "Grains & Staples"),
    ("Chickpeas 1kg", "Dried chickpeas, 1kg bag", 3.49, 80, "Grains & Staples"),
    ("Cocoa Powder 200g", "Unsweetened cocoa powder, 200g tin", 3.99, 60, "Grains & Staples"),
    ("Golden Meadow Honey", "Pure natural honey, 500g jar", 6.49, 50, "Grains & Staples"),
    ("Tahini 400g", "Stone-ground sesame tahini, 400g jar", 4.99, 60, "Grains & Staples"),
    ("Oranges 1kg", "Fresh juicy oranges, 1kg", 2.99, 110, "Fruits & Vegetables"),
    ("Strawberries 500g", "Fresh ripe strawberries, 500g box", 3.49, 60, "Fruits & Vegetables"),
    ("Grapes 1kg", "Fresh seedless grapes, 1kg", 4.49, 70, "Fruits & Vegetables"),
    ("Watermelon Whole", "Fresh whole watermelon", 5.99, 40, "Fruits & Vegetables"),
    ("Mango 1kg", "Fresh ripe mangoes, 1kg", 4.99, 65, "Fruits & Vegetables"),
    ("Lemon 1kg", "Fresh lemons, 1kg", 2.99, 100, "Fruits & Vegetables"),
    ("Garlic 250g", "Fresh garlic bulbs, 250g", 1.99, 100, "Fruits & Vegetables"),
    ("Potatoes 1kg", "Fresh potatoes, 1kg", 1.49, 130, "Fruits & Vegetables"),
    ("Carrots 1kg", "Fresh carrots, 1kg", 1.79, 110, "Fruits & Vegetables"),
    ("Zucchini 1kg", "Fresh zucchini, 1kg", 2.49, 100, "Fruits & Vegetables"),
    ("Eggplant 1kg", "Fresh eggplant, 1kg", 2.29, 100, "Fruits & Vegetables"),
    ("Bell Pepper 1kg", "Fresh mixed bell peppers, 1kg", 3.49, 90, "Fruits & Vegetables"),
    ("Baby Spinach 500g", "Fresh baby spinach leaves, 500g", 3.49, 80, "Fruits & Vegetables"),
    ("Lettuce Head", "Fresh crisp lettuce, 1 head", 1.49, 90, "Fruits & Vegetables"),
    ("Peach 1kg", "Fresh juicy peaches, 1kg", 4.49, 60, "Fruits & Vegetables"),
    ("Pear 1kg", "Fresh sweet pears, 1kg", 3.99, 65, "Fruits & Vegetables"),
    ("Guava 1kg", "Fresh pink guava, 1kg", 3.49, 70, "Fruits & Vegetables"),
    ("Pomegranate 1kg", "Fresh ruby pomegranate, 1kg", 5.99, 55, "Fruits & Vegetables"),
    ("Green Peas 500g", "Fresh green peas, 500g", 2.49, 75, "Fruits & Vegetables"),
    ("Green Beans 500g", "Fresh green beans, 500g", 2.29, 80, "Fruits & Vegetables"),
    ("Cauliflower Head", "Fresh cauliflower, 1 head", 2.49, 70, "Fruits & Vegetables"),
    ("Cabbage Head", "Fresh green cabbage, 1 head", 1.99, 85, "Fruits & Vegetables"),
    ("Molokhia Frozen 400g", "Frozen chopped molokhia greens, 400g", 2.99, 60, "Fruits & Vegetables"),
]

CATEGORIES = [
    "Beverages", "Dairy", "Bakery", "Snacks", "Grains & Staples", "Fruits & Vegetables"
]

# ===== Simple review text per product (no separate person/reviewer needed) =====
FIVE_STAR = [
    "Absolutely love this {product}! The quality is outstanding and it's become a staple in our kitchen.",
    "This {product} exceeded expectations. Fresh, high quality, and great value for the price.",
    "Best {product} available. Great taste and consistent quality every time.",
]
FOUR_STAR = [
    "Really good {product}, solid quality for the price. Would recommend to anyone looking for a reliable option.",
    "Pretty happy with this {product}. Good freshness and packaging overall.",
    "Good quality {product}. Does exactly what it says, minor room for improvement.",
]
THREE_STAR = [
    "Decent {product}, does the job but nothing extraordinary. Average quality for the price point.",
    "It's an okay {product}. Quality is acceptable for everyday use.",
]
RATING_POOLS = {5: FIVE_STAR, 4: FOUR_STAR, 3: THREE_STAR}


def generate_rating_and_review(name: str, seed_index: int):
    """Deterministic but varied: same product always gets the same rating/review
    on a fresh build, while still varying meaningfully across products."""
    rng = random.Random(seed_index)  # deterministic per product, not fully random
    rating = rng.choices([3, 4, 5], weights=[15, 40, 45])[0]
    template = rng.choice(RATING_POOLS[rating])
    review_text = template.format(product=name)
    return float(rating), review_text


def main():
    migrate(DB_PATH)
    conn = sqlite3.connect(DB_PATH)

    # Insert categories first
    for cat_name in CATEGORIES:
        conn.execute("INSERT OR IGNORE INTO category (name) VALUES (?);", (cat_name,))
    conn.commit()

    category_lookup = dict(conn.execute("SELECT name, category_id FROM category;").fetchall())

    # Insert products, already linked to the right category_id, with rating + review set directly
    rows = []
    existing_names = {row[0] for row in conn.execute("SELECT name FROM product")}

    for i, (name, desc, price, stock, category_name) in enumerate(PRODUCTS):
        if name in existing_names:
            continue
        props = PROPS_BY_NAME.get(name, "styled with a complementary prop beside it")
        image_prompt = IMAGE_PROMPT_TEMPLATE.format(name=name, props=props)
        image_path = f"products/images/{slugify(name)}.png"
        category_id = category_lookup[category_name]
        rating, review_text = generate_rating_and_review(name, seed_index=i)
        image_status = "done" if (PROJECT_ROOT / image_path).is_file() else "pending"
        rows.append((name, desc, price, stock, category_id, image_prompt, image_path, rating, review_text, image_status))

    conn.executemany(
        """
        INSERT INTO product
            (name, description, price, stock_quantity, category_id, image_prompt, image_path, avg_rating, review, image_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()

    count = conn.execute("SELECT COUNT(*) FROM product").fetchone()[0]
    done_count = conn.execute("SELECT COUNT(*) FROM product WHERE image_status = 'done'").fetchone()[0]
    pending_count = conn.execute("SELECT COUNT(*) FROM product WHERE image_status = 'pending'").fetchone()[0]
    print(f"Added {len(rows)} products; catalog contains {count} products in {DB_PATH}")
    print(f"Image status: {done_count} done, {pending_count} pending (need images generated)")
    print("Ratings and reviews set directly on each product (no separate reviewer accounts).")

    conn.close()
    print("Nutrition:", apply_catalog_nutrition(DB_PATH))


if __name__ == "__main__":
    main()