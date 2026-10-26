"""
models.py - the database tables.

Each class below is one table. SQLAlchemy turns these Python classes into
SQLite tables automatically (db.create_all() in app.py).
"""
from datetime import date, datetime

from flask import current_app
from flask_sqlalchemy import SQLAlchemy

from logic import expiry_label, expiry_state

db = SQLAlchemy()


# --------------------------------------------------------------------------
# Categories and storage locations
# --------------------------------------------------------------------------
class Category(db.Model):
    __tablename__ = "category"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(60), unique=True, nullable=False)
    icon = db.Column(db.String(8), default="🍽️")
    color = db.Column(db.String(9), default="#10b981")
    # Used to suggest an expiry date when you add a new item.
    default_shelf_days = db.Column(db.Integer, default=7)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "icon": self.icon,
            "color": self.color,
            "default_shelf_days": self.default_shelf_days,
        }


class StorageLocation(db.Model):
    __tablename__ = "storage_location"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(60), unique=True, nullable=False)
    icon = db.Column(db.String(8), default="🧊")

    def to_dict(self):
        return {"id": self.id, "name": self.name, "icon": self.icon}


# --------------------------------------------------------------------------
# Inventory
# --------------------------------------------------------------------------
class InventoryItem(db.Model):
    __tablename__ = "inventory_item"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"), nullable=False)
    location_id = db.Column(db.Integer, db.ForeignKey("storage_location.id"), nullable=False)
    quantity = db.Column(db.Float, nullable=False, default=1)
    # What you bought originally; used to work out the cost of what is consumed or wasted.
    initial_quantity = db.Column(db.Float, nullable=False, default=1)
    unit = db.Column(db.String(20), nullable=False, default="pcs")
    price = db.Column(db.Float, nullable=False, default=0)  # price paid for the whole purchase
    purchase_date = db.Column(db.Date, default=date.today)
    expiry_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.String(300), default="")
    status = db.Column(db.String(20), nullable=False, default="active")  # active | finished
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    category = db.relationship("Category")
    location = db.relationship("StorageLocation")

    def days_left(self, today=None):
        if self.expiry_date is None:
            return None
        return (self.expiry_date - (today or date.today())).days

    def to_dict(self):
        days = self.days_left()
        soon = current_app.config.get("EXPIRING_SOON_DAYS", 3)
        return {
            "id": self.id,
            "name": self.name,
            "category_id": self.category_id,
            "category": self.category.name if self.category else None,
            "category_icon": self.category.icon if self.category else "🍽️",
            "category_color": self.category.color if self.category else "#10b981",
            "location_id": self.location_id,
            "location": self.location.name if self.location else None,
            "location_icon": self.location.icon if self.location else "",
            "quantity": round(self.quantity, 3),
            "initial_quantity": round(self.initial_quantity, 3),
            "unit": self.unit,
            "price": round(self.price or 0, 2),
            "purchase_date": self.purchase_date.isoformat() if self.purchase_date else None,
            "expiry_date": self.expiry_date.isoformat() if self.expiry_date else None,
            "days_left": days,
            "state": expiry_state(days, soon),
            "expiry_label": expiry_label(days),
            "notes": self.notes or "",
            "status": self.status,
        }

    def as_match_dict(self):
        """Small dictionary used by logic.match_ingredients()."""
        days = self.days_left()
        return {
            "id": self.id,
            "name": self.name,
            "quantity": self.quantity,
            "unit": self.unit,
            "days_left": days,
            "state": expiry_state(days, current_app.config.get("EXPIRING_SOON_DAYS", 3)),
        }


# --------------------------------------------------------------------------
# Shopping list
# --------------------------------------------------------------------------
class ShoppingItem(db.Model):
    __tablename__ = "shopping_item"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    quantity = db.Column(db.Float, nullable=False, default=1)
    unit = db.Column(db.String(20), nullable=False, default="pcs")
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"), nullable=True)
    is_purchased = db.Column(db.Boolean, nullable=False, default=False)
    source = db.Column(db.String(30), default="manual")  # manual | recipe | restock
    added_at = db.Column(db.DateTime, default=datetime.now)

    category = db.relationship("Category")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "quantity": round(self.quantity, 3),
            "unit": self.unit,
            "category_id": self.category_id,
            "category": self.category.name if self.category else None,
            "category_icon": self.category.icon if self.category else "🛒",
            "is_purchased": self.is_purchased,
            "source": self.source,
            "added_at": self.added_at.isoformat() if self.added_at else None,
        }


# --------------------------------------------------------------------------
# Recipes
# --------------------------------------------------------------------------
class Recipe(db.Model):
    __tablename__ = "recipe"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    emoji = db.Column(db.String(8), default="🍲")
    description = db.Column(db.String(300), default="")
    instructions = db.Column(db.Text, default="")  # one step per line
    prep_minutes = db.Column(db.Integer, default=20)
    servings = db.Column(db.Integer, default=2)
    cuisine = db.Column(db.String(40), default="")
    diet = db.Column(db.String(30), default="Vegetarian")  # Vegan | Vegetarian | Non-Vegetarian
    is_favorite = db.Column(db.Boolean, default=False)

    ingredients = db.relationship(
        "RecipeIngredient", backref="recipe", cascade="all, delete-orphan", order_by="RecipeIngredient.id"
    )

    def ingredient_dicts(self):
        return [{"name": i.name, "quantity": i.quantity, "unit": i.unit} for i in self.ingredients]

    def base_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "emoji": self.emoji or "🍲",
            "description": self.description or "",
            "instructions": self.instructions or "",
            "steps": [s.strip() for s in (self.instructions or "").splitlines() if s.strip()],
            "prep_minutes": self.prep_minutes,
            "servings": self.servings,
            "cuisine": self.cuisine or "",
            "diet": self.diet or "",
            "is_favorite": bool(self.is_favorite),
        }


class RecipeIngredient(db.Model):
    __tablename__ = "recipe_ingredient"

    id = db.Column(db.Integer, primary_key=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey("recipe.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    quantity = db.Column(db.Float, nullable=False, default=1)
    unit = db.Column(db.String(20), nullable=False, default="pcs")


# --------------------------------------------------------------------------
# History tables (these power the analytics page)
# --------------------------------------------------------------------------
class ConsumptionLog(db.Model):
    __tablename__ = "consumption_log"

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, nullable=True)  # plain number so history survives item deletion
    item_name = db.Column(db.String(120), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"), nullable=True)
    quantity = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(20), nullable=False, default="pcs")
    cost = db.Column(db.Float, nullable=False, default=0)
    source = db.Column(db.String(60), default="manual")  # manual | recipe: <name>
    consumed_at = db.Column(db.DateTime, default=datetime.now)

    category = db.relationship("Category")

    def to_dict(self):
        return {
            "id": self.id,
            "item_name": self.item_name,
            "category": self.category.name if self.category else None,
            "quantity": round(self.quantity, 3),
            "unit": self.unit,
            "cost": round(self.cost, 2),
            "source": self.source,
            "consumed_at": self.consumed_at.isoformat() if self.consumed_at else None,
        }


class WasteLog(db.Model):
    __tablename__ = "waste_log"

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, nullable=True)
    item_name = db.Column(db.String(120), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"), nullable=True)
    quantity = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(20), nullable=False, default="pcs")
    cost = db.Column(db.Float, nullable=False, default=0)
    reason = db.Column(db.String(30), default="other")  # expired | spoiled | leftover | overbought | other
    wasted_at = db.Column(db.DateTime, default=datetime.now)

    category = db.relationship("Category")

    def to_dict(self):
        return {
            "id": self.id,
            "item_name": self.item_name,
            "category": self.category.name if self.category else None,
            "quantity": round(self.quantity, 3),
            "unit": self.unit,
            "cost": round(self.cost, 2),
            "reason": self.reason,
            "wasted_at": self.wasted_at.isoformat() if self.wasted_at else None,
        }


# --------------------------------------------------------------------------
# Notifications
# --------------------------------------------------------------------------
class Notification(db.Model):
    __tablename__ = "notification"

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(20), nullable=False)  # expired | expiring | info
    title = db.Column(db.String(160), nullable=False)
    message = db.Column(db.String(300), default="")
    item_id = db.Column(db.Integer, nullable=True)
    # Stops us creating the same alert twice for the same item.
    dedupe_key = db.Column(db.String(120), unique=True, nullable=True)
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "message": self.message,
            "item_id": self.item_id,
            "is_read": self.is_read,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
