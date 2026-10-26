"""
seed.py - fills an empty database with starting data.

Categories and storage locations are always added (the app needs them).
Demo food, recipes and history are added only when SEED_DEMO_ITEMS=1 (the default).
Dates are relative to today, so the demo always has some food expiring soon.
"""
import random
from datetime import date, datetime, timedelta

from models import (
    Category,
    ConsumptionLog,
    InventoryItem,
    Recipe,
    RecipeIngredient,
    ShoppingItem,
    StorageLocation,
    WasteLog,
    db,
)

CATEGORIES = [
    # name, icon, color, default shelf life in days
    ("Dairy", "🥛", "#3b82f6", 7),
    ("Vegetables", "🥦", "#10b981", 6),
    ("Fruits", "🍎", "#f43f5e", 6),
    ("Meat & Fish", "🍗", "#ef4444", 3),
    ("Grains & Bread", "🍞", "#f59e0b", 5),
    ("Beverages", "🧃", "#06b6d4", 30),
    ("Condiments", "🧂", "#a855f7", 180),
    ("Snacks & Sweets", "🍫", "#ec4899", 60),
    ("Leftovers", "🥡", "#64748b", 3),
    ("Other", "🍽️", "#94a3b8", 14),
]

LOCATIONS = [("Fridge", "🧊"), ("Freezer", "❄️"), ("Pantry", "🗄️"), ("Counter", "🧺")]

# name, category, location, quantity, unit, price, bought N days ago, expires in N days (None = no date)
ITEMS = [
    ("Whole Milk", "Dairy", "Fridge", 1.0, "l", 62, 4, 1),
    ("Greek Yogurt", "Dairy", "Fridge", 400, "g", 90, 3, 2),
    ("Paneer", "Dairy", "Fridge", 200, "g", 85, 2, 4),
    ("Eggs", "Dairy", "Fridge", 6, "pcs", 54, 5, 10),
    ("Butter", "Dairy", "Fridge", 100, "g", 58, 20, 45),
    ("Tomatoes", "Vegetables", "Fridge", 500, "g", 40, 3, 3),
    ("Spinach", "Vegetables", "Fridge", 250, "g", 30, 3, -1),
    ("Onions", "Vegetables", "Pantry", 1.0, "kg", 45, 6, 20),
    ("Potatoes", "Vegetables", "Pantry", 1.5, "kg", 60, 6, 25),
    ("Capsicum", "Vegetables", "Fridge", 3, "pcs", 36, 2, 5),
    ("Bananas", "Fruits", "Counter", 6, "pcs", 42, 2, 2),
    ("Apples", "Fruits", "Fridge", 4, "pcs", 120, 4, 12),
    ("Chicken Breast", "Meat & Fish", "Freezer", 500, "g", 210, 8, 30),
    ("Whole Wheat Bread", "Grains & Bread", "Counter", 1, "pack", 48, 3, 2),
    ("Basmati Rice", "Grains & Bread", "Pantry", 2, "kg", 260, 30, 300),
    ("Pasta", "Grains & Bread", "Pantry", 500, "g", 90, 25, 240),
    ("Orange Juice", "Beverages", "Fridge", 1, "l", 110, 5, 6),
    ("Tomato Ketchup", "Condiments", "Pantry", 1, "bottle", 120, 40, 150),
    ("Dal Makhani (leftover)", "Leftovers", "Fridge", 1, "pack", 0, 1, 2),
    ("Cheddar Cheese", "Dairy", "Fridge", 200, "g", 140, 7, 18),
]

# name, emoji, diet, cuisine, minutes, servings, description, [ingredients], steps
RECIPES = [
    ("Masala Omelette", "🍳", "Vegetarian", "Indian", 10, 1,
     "A quick, spicy breakfast that uses up onions and tomatoes.",
     [("Eggs", 3, "pcs"), ("Onions", 50, "g"), ("Tomatoes", 50, "g"), ("Butter", 10, "g")],
     ["Chop the onion and tomato finely.", "Beat the eggs with a pinch of salt and chilli.",
      "Melt the butter in a pan and fry the onion and tomato for 2 minutes.",
      "Pour in the eggs and cook until set. Fold and serve."]),
    ("Paneer Bhurji", "🧀", "Vegetarian", "Indian", 20, 2,
     "Scrambled paneer with onions, tomatoes and spices.",
     [("Paneer", 200, "g"), ("Onions", 100, "g"), ("Tomatoes", 150, "g"), ("Capsicum", 1, "pcs")],
     ["Crumble the paneer.", "Fry chopped onion until golden, then add tomato and capsicum.",
      "Add spices and the paneer and cook for 5 minutes.", "Serve with bread or roti."]),
    ("Spinach Omelette", "🥬", "Vegetarian", "Continental", 12, 1,
     "Use spinach before it goes off.",
     [("Eggs", 3, "pcs"), ("Spinach", 100, "g"), ("Butter", 10, "g"), ("Cheddar Cheese", 30, "g")],
     ["Wilt the spinach in butter for 1 minute.", "Pour in beaten eggs.",
      "Sprinkle grated cheese, fold and serve."]),
    ("Tomato Pasta", "🍝", "Vegetarian", "Italian", 25, 2,
     "A simple weeknight pasta.",
     [("Pasta", 200, "g"), ("Tomatoes", 300, "g"), ("Onions", 1, "pcs"), ("Cheddar Cheese", 40, "g")],
     ["Boil the pasta in salted water.", "Cook chopped onion and tomatoes into a sauce.",
      "Toss the pasta in the sauce and top with cheese."]),
    ("Aloo Sabzi", "🥔", "Vegan", "Indian", 30, 3,
     "Everyday spiced potatoes.",
     [("Potatoes", 500, "g"), ("Onions", 100, "g"), ("Tomatoes", 100, "g")],
     ["Boil and cube the potatoes.", "Fry onion, add tomato and spices.",
      "Add the potatoes and cook for 8 minutes."]),
    ("Banana Smoothie", "🍌", "Vegetarian", "Drinks", 5, 1,
     "Uses over-ripe bananas and milk before they expire.",
     [("Bananas", 2, "pcs"), ("Whole Milk", 250, "ml"), ("Greek Yogurt", 50, "g")],
     ["Peel and chop the bananas.", "Blend everything until smooth.", "Serve cold."]),
    ("Egg Fried Rice", "🍚", "Vegetarian", "Chinese", 20, 2,
     "Great for leftover rice.",
     [("Basmati Rice", 200, "g"), ("Eggs", 2, "pcs"), ("Capsicum", 1, "pcs"), ("Onions", 50, "g")],
     ["Cook and cool the rice.", "Scramble the eggs and set aside.",
      "Stir-fry onion and capsicum, add rice and eggs, season and serve."]),
    ("Chicken Stir-fry", "🍗", "Non-Vegetarian", "Asian", 25, 2,
     "High-protein dinner with vegetables.",
     [("Chicken Breast", 300, "g"), ("Capsicum", 2, "pcs"), ("Onions", 1, "pcs"), ("Tomato Ketchup", 2, "tbsp".replace("tbsp", "pcs"))],
     ["Thaw and slice the chicken.", "Fry the chicken until golden.",
      "Add vegetables and a little ketchup and stir-fry for 5 minutes."]),
    ("French Toast", "🍞", "Vegetarian", "Breakfast", 15, 2,
     "Rescues bread that is going stale.",
     [("Whole Wheat Bread", 1, "pack"), ("Eggs", 2, "pcs"), ("Whole Milk", 100, "ml"), ("Butter", 20, "g")],
     ["Whisk eggs and milk.", "Dip each slice in the mix.", "Fry in butter until golden on both sides."]),
    ("Cheese Sandwich", "🥪", "Vegetarian", "Snacks", 8, 1,
     "Fast lunch box option.",
     [("Whole Wheat Bread", 1, "pack"), ("Cheddar Cheese", 50, "g"), ("Tomatoes", 50, "g"), ("Butter", 10, "g")],
     ["Butter the bread.", "Layer cheese and tomato.", "Toast in a pan until crisp."]),
    ("Fruit Yogurt Bowl", "🍎", "Vegetarian", "Breakfast", 5, 1,
     "No cooking needed.",
     [("Greek Yogurt", 200, "g"), ("Apples", 1, "pcs"), ("Bananas", 1, "pcs")],
     ["Chop the fruit.", "Spoon yogurt into a bowl and top with fruit."]),
    ("Palak Paneer", "🥘", "Vegetarian", "Indian", 35, 3,
     "Classic spinach and paneer curry.",
     [("Spinach", 250, "g"), ("Paneer", 200, "g"), ("Onions", 100, "g"), ("Tomatoes", 100, "g")],
     ["Blanch the spinach and blend to a puree.", "Fry onion and tomato with spices.",
      "Add the puree and paneer and simmer for 8 minutes."]),
]

SHOPPING = [("Coriander", 1, "pack", "Vegetables"), ("Curd", 500, "g", "Dairy"), ("Lemons", 4, "pcs", "Fruits")]


def seed_basics():
    """Categories and locations. Safe to call many times."""
    if Category.query.count() == 0:
        for name, icon, color, shelf in CATEGORIES:
            db.session.add(Category(name=name, icon=icon, color=color, default_shelf_days=shelf))
    if StorageLocation.query.count() == 0:
        for name, icon in LOCATIONS:
            db.session.add(StorageLocation(name=name, icon=icon))
    db.session.commit()


def seed_demo():
    """Demo food, recipes, shopping list and history. Only runs on an empty database."""
    if InventoryItem.query.count() or Recipe.query.count():
        return
    cats = {c.name: c for c in Category.query.all()}
    locs = {l.name: l for l in StorageLocation.query.all()}
    today = date.today()

    for name, cat, loc, qty, unit, price, bought, expires in ITEMS:
        db.session.add(InventoryItem(
            name=name, category_id=cats[cat].id, location_id=locs[loc].id,
            quantity=qty, initial_quantity=qty, unit=unit, price=price,
            purchase_date=today - timedelta(days=bought),
            expiry_date=None if expires is None else today + timedelta(days=expires),
        ))

    for name, emoji, diet, cuisine, minutes, servings, desc, ingredients, steps in RECIPES:
        recipe = Recipe(
            name=name, emoji=emoji, diet=diet, cuisine=cuisine, prep_minutes=minutes,
            servings=servings, description=desc, instructions="\n".join(steps),
        )
        for ing_name, ing_qty, ing_unit in ingredients:
            recipe.ingredients.append(RecipeIngredient(name=ing_name, quantity=ing_qty, unit=ing_unit))
        db.session.add(recipe)

    for name, qty, unit, cat in SHOPPING:
        db.session.add(ShoppingItem(name=name, quantity=qty, unit=unit, category_id=cats[cat].id))

    # A fixed random seed keeps the demo history the same every time.
    rng = random.Random(42)
    eaten = [
        ("Eggs", "Dairy", 3, "pcs", 27), ("Whole Milk", "Dairy", 0.5, "l", 31),
        ("Tomatoes", "Vegetables", 200, "g", 16), ("Bananas", "Fruits", 2, "pcs", 14),
        ("Greek Yogurt", "Dairy", 150, "g", 34), ("Apples", "Fruits", 1, "pcs", 30),
        ("Onions", "Vegetables", 150, "g", 7), ("Paneer", "Dairy", 100, "g", 42),
        ("Whole Wheat Bread", "Grains & Bread", 1, "pack", 48), ("Orange Juice", "Beverages", 0.5, "l", 55),
    ]
    for _ in range(26):
        name, cat, qty, unit, cost = rng.choice(eaten)
        when = datetime.now() - timedelta(days=rng.randint(0, 29), hours=rng.randint(0, 12))
        db.session.add(ConsumptionLog(
            item_name=name, category_id=cats[cat].id, quantity=qty, unit=unit,
            cost=cost, source="manual", consumed_at=when,
        ))

    wasted = [
        ("Spinach", "Vegetables", 150, "g", 18, "expired"), ("Leftover Rice", "Leftovers", 1, "pack", 15, "leftover"),
        ("Bread", "Grains & Bread", 1, "pack", 48, "spoiled"), ("Strawberries", "Fruits", 250, "g", 80, "spoiled"),
        ("Milk", "Dairy", 0.5, "l", 31, "expired"), ("Cucumber", "Vegetables", 2, "pcs", 20, "spoiled"),
        ("Yogurt", "Dairy", 200, "g", 45, "expired"), ("Chicken Curry", "Leftovers", 1, "pack", 90, "leftover"),
    ]
    for name, cat, qty, unit, cost, reason in wasted:
        when = datetime.now() - timedelta(days=rng.randint(1, 28), hours=rng.randint(0, 12))
        db.session.add(WasteLog(
            item_name=name, category_id=cats[cat].id, quantity=qty, unit=unit,
            cost=cost, reason=reason, wasted_at=when,
        ))

    db.session.commit()
