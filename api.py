"""
api.py - the REST API. The web pages call these URLs with fetch().

Every URL starts with /api. Data goes in and out as JSON.
Mistakes (like a missing name) return a 400 error with a clear message.
"""
import math
from datetime import date

from flask import Blueprint, jsonify, request

import services as svc
from logic import UNITS, convert, match_ingredients, names_match
from models import (
    Category,
    ConsumptionLog,
    InventoryItem,
    Notification,
    Recipe,
    RecipeIngredient,
    ShoppingItem,
    StorageLocation,
    WasteLog,
    db,
)

api = Blueprint("api", __name__, url_prefix="/api")

WASTE_REASONS = ["expired", "spoiled", "leftover", "overbought", "other"]
DIETS = ["Vegan", "Vegetarian", "Non-Vegetarian"]


# --------------------------------------------------------------------------
# Small validation helpers
# --------------------------------------------------------------------------
class ApiError(Exception):
    def __init__(self, message, status=400, field=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.field = field


@api.errorhandler(ApiError)
def handle_api_error(err):
    return jsonify({"error": err.message, "field": err.field}), err.status


def body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError("Please send the data as JSON.")
    return data


def get_or_404(model, ident, label=None):
    obj = db.session.get(model, ident)
    if obj is None:
        raise ApiError(f"{label or model.__name__} not found.", 404)
    return obj


def parse_text(value, field, max_len, required=False):
    text = "" if value is None else str(value).strip()
    if required and not text:
        raise ApiError(f"{field.replace('_', ' ').capitalize()} is required.", field=field)
    if len(text) > max_len:
        raise ApiError(f"{field.replace('_', ' ').capitalize()} must be at most {max_len} characters.", field=field)
    return text


def parse_number(value, field, minimum=None, exclusive_min=False, default=None, maximum=1_000_000):
    label = field.replace("_", " ").capitalize()
    if value is None or value == "":
        if default is not None:
            return default
        raise ApiError(f"{label} is required.", field=field)
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ApiError(f"{label} must be a number.", field=field)
    if math.isnan(number) or math.isinf(number):
        raise ApiError(f"{label} must be a number.", field=field)
    if minimum is not None:
        if exclusive_min and number <= minimum:
            raise ApiError(f"{label} must be greater than {minimum:g}.", field=field)
        if not exclusive_min and number < minimum:
            raise ApiError(f"{label} cannot be less than {minimum:g}.", field=field)
    if number > maximum:
        raise ApiError(f"{label} is too large.", field=field)
    return number


def parse_date(value, field):
    if value is None or value == "":
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        raise ApiError(f"{field.replace('_', ' ').capitalize()} must be a date like 2026-12-31.", field=field)


def parse_ref(value, field, model, label, required=True):
    if value is None or value == "":
        if required:
            raise ApiError(f"Please choose a {label}.", field=field)
        return None
    try:
        ident = int(value)
    except (TypeError, ValueError):
        raise ApiError(f"Please choose a valid {label}.", field=field)
    if db.session.get(model, ident) is None:
        raise ApiError(f"Unknown {label}.", field=field)
    return ident


def parse_unit(value, field="unit"):
    unit = str(value or "pcs").strip().lower()
    if unit not in UNITS:
        raise ApiError(f"Unit must be one of: {', '.join(UNITS)}.", field=field)
    return unit


def validate_item(data, current=None):
    """Check the data for an inventory item. `current` supplies defaults when editing."""
    cur = current or {}

    def pick(key, default=None):
        return data[key] if key in data else cur.get(key, default)

    purchase_date = parse_date(pick("purchase_date"), "purchase_date") or date.today()
    expiry_date = parse_date(pick("expiry_date"), "expiry_date")
    if expiry_date and expiry_date < purchase_date:
        raise ApiError("Expiry date cannot be before the purchase date.", field="expiry_date")

    return {
        "name": parse_text(pick("name"), "name", 120, required=True),
        "category_id": parse_ref(pick("category_id"), "category_id", Category, "category"),
        "location_id": parse_ref(pick("location_id"), "location_id", StorageLocation, "storage location"),
        "quantity": parse_number(pick("quantity"), "quantity", minimum=0, exclusive_min=True),
        "unit": parse_unit(pick("unit", "pcs")),
        "price": parse_number(pick("price", 0), "price", minimum=0, default=0),
        "purchase_date": purchase_date,
        "expiry_date": expiry_date,
        "notes": parse_text(pick("notes", ""), "notes", 300),
    }


# --------------------------------------------------------------------------
# Meta: categories, locations, units
# --------------------------------------------------------------------------
@api.get("/categories")
def list_categories():
    return jsonify([c.to_dict() for c in Category.query.order_by(Category.name).all()])


@api.get("/locations")
def list_locations():
    return jsonify([l.to_dict() for l in StorageLocation.query.order_by(StorageLocation.id).all()])


@api.get("/units")
def list_units():
    return jsonify(UNITS)


# --------------------------------------------------------------------------
# Inventory items
# --------------------------------------------------------------------------
@api.get("/items")
def list_items():
    query = InventoryItem.query
    if request.args.get("include_finished") != "1":
        query = query.filter_by(status="active")
    category_id = request.args.get("category_id", type=int)
    if category_id:
        query = query.filter_by(category_id=category_id)
    location_id = request.args.get("location_id", type=int)
    if location_id:
        query = query.filter_by(location_id=location_id)

    items = query.all()
    search = (request.args.get("q") or "").strip().lower()
    if search:
        items = [i for i in items if search in i.name.lower() or search in (i.notes or "").lower()]

    rows = [i.to_dict() for i in items]
    state = request.args.get("state")
    if state:
        rows = [r for r in rows if r["state"] == state]

    sort = request.args.get("sort", "expiry")
    if sort == "name":
        rows.sort(key=lambda r: r["name"].lower())
    elif sort == "recent":
        rows.sort(key=lambda r: -r["id"])
    elif sort == "category":
        rows.sort(key=lambda r: (r["category"] or "", r["name"].lower()))
    else:  # expiry: soonest first, items without a date last
        rows.sort(key=lambda r: (r["days_left"] is None, r["days_left"] or 0, r["name"].lower()))
    return jsonify(rows)


@api.post("/items")
def create_item():
    clean = validate_item(body())
    item = InventoryItem(**clean, initial_quantity=clean["quantity"])
    db.session.add(item)
    db.session.commit()
    svc.refresh_notifications()
    return jsonify(item.to_dict()), 201


@api.get("/items/<int:item_id>")
def get_item(item_id):
    return jsonify(get_or_404(InventoryItem, item_id, "Item").to_dict())


@api.put("/items/<int:item_id>")
def update_item(item_id):
    item = get_or_404(InventoryItem, item_id, "Item")
    clean = validate_item(body(), current=item.to_dict())
    for key, value in clean.items():
        setattr(item, key, value)
    item.initial_quantity = max(item.initial_quantity or 0, item.quantity)
    item.status = "active"  # editing a finished item with a quantity brings it back
    db.session.commit()
    svc.refresh_notifications()
    return jsonify(item.to_dict())


@api.delete("/items/<int:item_id>")
def delete_item(item_id):
    item = get_or_404(InventoryItem, item_id, "Item")
    Notification.query.filter_by(item_id=item.id).delete()
    db.session.delete(item)
    db.session.commit()
    return jsonify({"deleted": item_id})


def _take(item_id, kind):
    item = get_or_404(InventoryItem, item_id, "Item")
    data = body()
    if item.status != "active" or item.quantity <= 0:
        raise ApiError("This item is already finished.")
    qty = parse_number(data.get("quantity"), "quantity", minimum=0, exclusive_min=True, default=item.quantity)
    if qty > item.quantity + 1e-9:
        raise ApiError(f"You only have {item.quantity:g} {item.unit} of {item.name}.", field="quantity")

    reason = "other"
    if kind == "waste":
        reason = str(data.get("reason") or ("expired" if (item.days_left() or 0) < 0 else "other")).lower()
        if reason not in WASTE_REASONS:
            raise ApiError(f"Reason must be one of: {', '.join(WASTE_REASONS)}.", field="reason")

    log = svc.take_from_item(item, qty, kind, reason=reason)
    db.session.commit()
    svc.refresh_notifications()
    return jsonify({"item": item.to_dict(), "log": log.to_dict()})


@api.post("/items/<int:item_id>/consume")
def consume_item(item_id):
    return _take(item_id, "consume")


@api.post("/items/<int:item_id>/waste")
def waste_item(item_id):
    return _take(item_id, "waste")


# --------------------------------------------------------------------------
# Shopping list
# --------------------------------------------------------------------------
@api.get("/shopping")
def list_shopping():
    rows = ShoppingItem.query.order_by(ShoppingItem.is_purchased, ShoppingItem.added_at.desc()).all()
    return jsonify([r.to_dict() for r in rows])


def _add_shopping(name, quantity, unit, category_id, source):
    """Add to the list, or top up an existing unpurchased line with the same name and unit."""
    existing = ShoppingItem.query.filter_by(is_purchased=False, unit=unit).all()
    for row in existing:
        if row.name.strip().lower() == name.strip().lower():
            row.quantity += quantity
            return row, False
    row = ShoppingItem(name=name, quantity=quantity, unit=unit, category_id=category_id, source=source)
    db.session.add(row)
    return row, True


@api.post("/shopping")
def create_shopping():
    data = body()
    name = parse_text(data.get("name"), "name", 120, required=True)
    qty = parse_number(data.get("quantity"), "quantity", minimum=0, exclusive_min=True, default=1)
    unit = parse_unit(data.get("unit"))
    category_id = parse_ref(data.get("category_id"), "category_id", Category, "category", required=False)
    row, created = _add_shopping(name, qty, unit, category_id, "manual")
    db.session.commit()
    return jsonify(row.to_dict()), 201 if created else 200


@api.put("/shopping/<int:row_id>")
def update_shopping(row_id):
    row = get_or_404(ShoppingItem, row_id, "Shopping item")
    data = body()
    if "name" in data:
        row.name = parse_text(data["name"], "name", 120, required=True)
    if "quantity" in data:
        row.quantity = parse_number(data["quantity"], "quantity", minimum=0, exclusive_min=True)
    if "unit" in data:
        row.unit = parse_unit(data["unit"])
    if "category_id" in data:
        row.category_id = parse_ref(data["category_id"], "category_id", Category, "category", required=False)
    db.session.commit()
    return jsonify(row.to_dict())


@api.post("/shopping/<int:row_id>/toggle")
def toggle_shopping(row_id):
    row = get_or_404(ShoppingItem, row_id, "Shopping item")
    row.is_purchased = not row.is_purchased
    db.session.commit()
    return jsonify(row.to_dict())


@api.delete("/shopping/<int:row_id>")
def delete_shopping(row_id):
    row = get_or_404(ShoppingItem, row_id, "Shopping item")
    db.session.delete(row)
    db.session.commit()
    return jsonify({"deleted": row_id})


@api.post("/shopping/clear-purchased")
def clear_purchased():
    count = ShoppingItem.query.filter_by(is_purchased=True).delete()
    db.session.commit()
    return jsonify({"deleted": count})


@api.post("/shopping/<int:row_id>/to-inventory")
def shopping_to_inventory(row_id):
    """Move a bought item from the shopping list into the fridge."""
    row = get_or_404(ShoppingItem, row_id, "Shopping item")
    data = body()
    category = row.category_id or data.get("category_id")
    clean = validate_item({
        "name": row.name,
        "category_id": data.get("category_id", category),
        "location_id": data.get("location_id"),
        "quantity": data.get("quantity", row.quantity),
        "unit": row.unit,
        "price": data.get("price", 0),
        "purchase_date": data.get("purchase_date"),
        "expiry_date": data.get("expiry_date"),
        "notes": data.get("notes", ""),
    })
    item = InventoryItem(**clean, initial_quantity=clean["quantity"])
    db.session.add(item)
    db.session.delete(row)
    db.session.commit()
    svc.refresh_notifications()
    return jsonify(item.to_dict()), 201


@api.get("/shopping/suggestions")
def shopping_suggestions():
    """Things you finished that are not on the list yet."""
    on_list = [r.name for r in ShoppingItem.query.filter_by(is_purchased=False).all()]
    seen, suggestions = set(), []
    finished = InventoryItem.query.filter_by(status="finished").order_by(InventoryItem.updated_at.desc()).all()
    for item in finished:
        key = item.name.strip().lower()
        if key in seen or any(names_match(item.name, n) for n in on_list):
            continue
        seen.add(key)
        suggestions.append({
            "name": item.name,
            "unit": item.unit,
            "quantity": round(item.initial_quantity or 1, 3),
            "category_id": item.category_id,
            "category_icon": item.category.icon if item.category else "🛒",
        })
        if len(suggestions) >= 8:
            break
    return jsonify(suggestions)


# --------------------------------------------------------------------------
# Recipes
# --------------------------------------------------------------------------
def validate_recipe(data):
    name = parse_text(data.get("name"), "name", 120, required=True)
    diet = str(data.get("diet") or "Vegetarian")
    if diet not in DIETS:
        raise ApiError(f"Diet must be one of: {', '.join(DIETS)}.", field="diet")
    raw = data.get("ingredients")
    if not isinstance(raw, list) or not raw:
        raise ApiError("Add at least one ingredient.", field="ingredients")
    ingredients = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise ApiError("Each ingredient needs a name, quantity and unit.", field="ingredients")
        ingredients.append({
            "name": parse_text(entry.get("name"), "ingredient_name", 120, required=True),
            "quantity": parse_number(entry.get("quantity"), "ingredient_quantity", minimum=0, exclusive_min=True, default=1),
            "unit": parse_unit(entry.get("unit"), "ingredient_unit"),
        })
    return {
        "name": name,
        "emoji": parse_text(data.get("emoji") or "🍲", "emoji", 8),
        "description": parse_text(data.get("description"), "description", 300),
        "instructions": parse_text(data.get("instructions"), "instructions", 4000),
        "prep_minutes": int(parse_number(data.get("prep_minutes"), "prep_minutes", minimum=1, default=20, maximum=1440)),
        "servings": int(parse_number(data.get("servings"), "servings", minimum=1, default=2, maximum=50)),
        "cuisine": parse_text(data.get("cuisine"), "cuisine", 40),
        "diet": diet,
    }, ingredients


@api.get("/recipes")
def list_recipes():
    rows = svc.all_recipes_with_match()

    search = (request.args.get("q") or "").strip().lower()
    if search:
        rows = [
            r for r in rows
            if search in r["name"].lower()
            or search in r["cuisine"].lower()
            or any(search in i["name"].lower() for i in r["ingredients"])
        ]
    diet = request.args.get("diet")
    if diet:
        rows = [r for r in rows if r["diet"] == diet]
    max_time = request.args.get("max_time", type=int)
    if max_time:
        rows = [r for r in rows if r["prep_minutes"] <= max_time]
    if request.args.get("can_cook") == "1":
        rows = [r for r in rows if r["can_cook"]]
    if request.args.get("favorites") == "1":
        rows = [r for r in rows if r["is_favorite"]]
    if request.args.get("uses_expiring") == "1":
        rows = [r for r in rows if r["expiring_used"] > 0]

    sort = request.args.get("sort", "smart")
    if sort == "time":
        rows.sort(key=lambda r: (r["prep_minutes"], r["name"]))
    elif sort == "name":
        rows.sort(key=lambda r: r["name"])
    else:  # smart: best match first, recipes that rescue expiring food get a boost
        rows.sort(key=lambda r: (-r["score"], r["name"]))
    return jsonify(rows)


@api.get("/recipes/<int:recipe_id>")
def get_recipe(recipe_id):
    recipe = get_or_404(Recipe, recipe_id, "Recipe")
    return jsonify(svc.recipe_with_match(recipe, [i.as_match_dict() for i in svc.active_items()]))


@api.post("/recipes")
def create_recipe():
    fields, ingredients = validate_recipe(body())
    recipe = Recipe(**fields)
    for ing in ingredients:
        recipe.ingredients.append(RecipeIngredient(**ing))
    db.session.add(recipe)
    db.session.commit()
    return jsonify(svc.recipe_with_match(recipe, [i.as_match_dict() for i in svc.active_items()])), 201


@api.delete("/recipes/<int:recipe_id>")
def delete_recipe(recipe_id):
    recipe = get_or_404(Recipe, recipe_id, "Recipe")
    db.session.delete(recipe)
    db.session.commit()
    return jsonify({"deleted": recipe_id})


@api.post("/recipes/<int:recipe_id>/favorite")
def toggle_favorite(recipe_id):
    recipe = get_or_404(Recipe, recipe_id, "Recipe")
    recipe.is_favorite = not recipe.is_favorite
    db.session.commit()
    return jsonify({"id": recipe.id, "is_favorite": recipe.is_favorite})


@api.post("/recipes/<int:recipe_id>/add-missing")
def add_missing_to_shopping(recipe_id):
    recipe = get_or_404(Recipe, recipe_id, "Recipe")
    info = svc.recipe_with_match(recipe, [i.as_match_dict() for i in svc.active_items()])
    added = []
    for ing in info["ingredients"]:
        # Missing, or present but not enough for this recipe.
        if ing["have"] and ing["enough"] is not False:
            continue
        row, _ = _add_shopping(ing["name"], ing["quantity"], ing["unit"], None, "recipe")
        added.append(ing["name"])
    db.session.commit()
    return jsonify({"added": added, "count": len(added)})


@api.post("/recipes/<int:recipe_id>/cook")
def cook_recipe(recipe_id):
    """Mark a recipe as cooked: use up the ingredients you have and record it in the history."""
    recipe = get_or_404(Recipe, recipe_id, "Recipe")
    items = svc.active_items()
    by_id = {i.id: i for i in items}
    matches = match_ingredients(recipe.ingredient_dicts(), [i.as_match_dict() for i in items])

    deducted, skipped = [], []
    for m in matches:
        if not m["have"]:
            skipped.append({"name": m["name"], "reason": "not in your fridge"})
            continue
        item = by_id[m["item_id"]]
        needed = convert(m["quantity"], m["unit"], item.unit)
        if needed is None:
            skipped.append({
                "name": m["name"],
                "reason": f"units differ ({m['unit']} vs {item.unit}) - adjust {item.name} by hand",
            })
            continue
        used = min(needed, item.quantity)
        if used <= 0:
            skipped.append({"name": m["name"], "reason": "already used up"})
            continue
        svc.take_from_item(item, used, "consume", source=f"recipe: {recipe.name}"[:60])
        deducted.append({
            "name": item.name, "quantity": round(used, 3), "unit": item.unit,
            "short": needed > used + 1e-9,
        })

    if not deducted:
        raise ApiError("None of the ingredients could be used up, so nothing was changed.")
    db.session.commit()
    svc.refresh_notifications()
    return jsonify({"recipe": recipe.name, "deducted": deducted, "skipped": skipped})


# --------------------------------------------------------------------------
# Notifications
# --------------------------------------------------------------------------
@api.get("/notifications")
def list_notifications():
    svc.refresh_notifications()
    query = Notification.query
    if request.args.get("unread") == "1":
        query = query.filter_by(is_read=False)
    rows = query.order_by(Notification.is_read, Notification.created_at.desc(), Notification.id.desc()).all()
    return jsonify({"items": [n.to_dict() for n in rows], "unread": svc.unread_count()})


@api.get("/notifications/unread-count")
def notifications_unread_count():
    svc.refresh_notifications()
    return jsonify({"unread": svc.unread_count()})


@api.post("/notifications/<int:note_id>/read")
def mark_read(note_id):
    note = get_or_404(Notification, note_id, "Notification")
    note.is_read = True
    db.session.commit()
    return jsonify(note.to_dict())


@api.post("/notifications/read-all")
def mark_all_read():
    count = Notification.query.filter_by(is_read=False).update({"is_read": True})
    db.session.commit()
    return jsonify({"updated": count})


@api.delete("/notifications/<int:note_id>")
def delete_notification(note_id):
    note = get_or_404(Notification, note_id, "Notification")
    db.session.delete(note)
    db.session.commit()
    return jsonify({"deleted": note_id})


# --------------------------------------------------------------------------
# Dashboard and analytics
# --------------------------------------------------------------------------
@api.get("/dashboard")
def dashboard():
    return jsonify(svc.dashboard_data())


@api.get("/analytics")
def analytics():
    days = request.args.get("days", 30, type=int)
    if days not in (7, 30, 90):
        days = 30
    return jsonify(svc.analytics_overview(days))


@api.get("/history")
def history():
    """Recent consumption and waste records (used for the history lists)."""
    limit = min(request.args.get("limit", 20, type=int), 100)
    consumed = ConsumptionLog.query.order_by(ConsumptionLog.consumed_at.desc()).limit(limit).all()
    wasted = WasteLog.query.order_by(WasteLog.wasted_at.desc()).limit(limit).all()
    return jsonify({
        "consumed": [c.to_dict() for c in consumed],
        "wasted": [w.to_dict() for w in wasted],
    })
