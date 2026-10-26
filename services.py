"""
services.py - the "business logic" that talks to the database.

The API routes in api.py stay short because the real work happens here.
"""
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta

from flask import current_app

from logic import expiry_label, match_ingredients, summarize_match
from models import (
    Category,
    ConsumptionLog,
    InventoryItem,
    Notification,
    Recipe,
    ShoppingItem,
    WasteLog,
    db,
)


# --------------------------------------------------------------------------
# Inventory helpers
# --------------------------------------------------------------------------
def active_items():
    return InventoryItem.query.filter_by(status="active").all()


def cost_of(item, qty):
    """Share of the purchase price that belongs to `qty` units of this item."""
    base = item.initial_quantity or item.quantity or 1
    return round((item.price or 0) * qty / base, 2)


def take_from_item(item, qty, kind, reason="other", source="manual"):
    """
    Remove `qty` from an item and write a history row.
    kind is "consume" (eaten/used) or "waste" (thrown away).
    The caller is responsible for db.session.commit().
    """
    cost = cost_of(item, qty)
    item.quantity = round(item.quantity - qty, 4)
    if item.quantity <= 0.0001:
        item.quantity = 0
        item.status = "finished"

    if kind == "consume":
        log = ConsumptionLog(
            item_id=item.id, item_name=item.name, category_id=item.category_id,
            quantity=qty, unit=item.unit, cost=cost, source=source,
        )
    else:
        log = WasteLog(
            item_id=item.id, item_name=item.name, category_id=item.category_id,
            quantity=qty, unit=item.unit, cost=cost, reason=reason,
        )
    db.session.add(log)
    return log


# --------------------------------------------------------------------------
# Notifications
# --------------------------------------------------------------------------
def refresh_notifications():
    """
    Look at the fridge and make sure every expired / expiring item has exactly
    one notification. Old alerts that no longer apply are removed.
    """
    soon = current_app.config.get("EXPIRING_SOON_DAYS", 3)
    today = date.today()

    items = InventoryItem.query.filter(
        InventoryItem.status == "active", InventoryItem.expiry_date.isnot(None)
    ).all()
    existing = {
        n.dedupe_key: n for n in Notification.query.filter(Notification.dedupe_key.isnot(None)).all()
    }

    valid_keys = set()
    for item in items:
        days = item.days_left(today)
        if days > soon:
            continue
        kind = "expired" if days < 0 else "expiring"
        key = f"{kind}:{item.id}:{item.expiry_date.isoformat()}"
        valid_keys.add(key)
        if key in existing:
            continue
        if kind == "expired":
            title = f"{item.name} has expired"
            message = f"{expiry_label(days)}. Remove it or log it as waste."
        else:
            title = f"{item.name}: {expiry_label(days).lower()}"
            message = "Use it soon - check the Recipes page for ideas."
        note = Notification(kind=kind, title=title, message=message, item_id=item.id, dedupe_key=key)
        db.session.add(note)
        existing[key] = note

    for key, note in existing.items():
        if note.kind in ("expired", "expiring") and key not in valid_keys:
            db.session.delete(note)

    db.session.commit()


def unread_count():
    return Notification.query.filter_by(is_read=False).count()


# --------------------------------------------------------------------------
# Recipes
# --------------------------------------------------------------------------
def recipe_with_match(recipe, item_dicts):
    """Recipe dictionary plus which ingredients you have / are missing."""
    results = match_ingredients(recipe.ingredient_dicts(), item_dicts)
    data = recipe.base_dict()
    data["ingredients"] = results
    data.update(summarize_match(results))
    data["missing"] = [r for r in results if not r["have"]]
    return data


def all_recipes_with_match():
    item_dicts = [i.as_match_dict() for i in active_items()]
    return [recipe_with_match(r, item_dicts) for r in Recipe.query.order_by(Recipe.name).all()]


# --------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------
def inventory_value(items):
    total = 0.0
    for i in items:
        base = i.initial_quantity or i.quantity or 1
        total += (i.price or 0) * i.quantity / base
    return round(total, 2)


def category_breakdown(items):
    counts = Counter()
    colors = {}
    for i in items:
        name = i.category.name if i.category else "Other"
        counts[name] += 1
        colors[name] = i.category.color if i.category else "#94a3b8"
    return [{"name": n, "count": c, "color": colors[n]} for n, c in counts.most_common()]


def activity_series(days):
    """Per-day number of items consumed and wasted for the last `days` days."""
    today = date.today()
    start = datetime.combine(today - timedelta(days=days - 1), time.min)
    consumed = Counter(
        c.consumed_at.date() for c in ConsumptionLog.query.filter(ConsumptionLog.consumed_at >= start)
    )
    wasted = Counter(w.wasted_at.date() for w in WasteLog.query.filter(WasteLog.wasted_at >= start))
    labels, cons, waste = [], [], []
    for offset in range(days):
        d = today - timedelta(days=days - 1 - offset)
        labels.append(d.isoformat())
        cons.append(consumed.get(d, 0))
        waste.append(wasted.get(d, 0))
    return {"labels": labels, "consumed": cons, "wasted": waste}


def dashboard_data():
    refresh_notifications()
    items = active_items()
    dicts = [i.to_dict() for i in items]

    expired = [d for d in dicts if d["state"] == "expired"]
    expiring = [d for d in dicts if d["state"] == "expiring"]
    fresh = [d for d in dicts if d["state"] in ("fresh", "none")]
    attention = sorted(expired + expiring, key=lambda d: d["days_left"])[:8]

    match_dicts = [i.as_match_dict() for i in items]
    recipes = [recipe_with_match(r, match_dicts) for r in Recipe.query.all()]
    recipes = [r for r in recipes if r["match_pct"] > 0]
    recipes.sort(key=lambda r: (-r["score"], r["name"]))
    # Keep the payload small for the dashboard.
    suggestions = []
    for r in recipes[:3]:
        suggestions.append({k: r[k] for k in (
            "id", "name", "emoji", "prep_minutes", "match_pct", "have_count",
            "total_count", "expiring_used", "can_cook",
        )})

    shopping = ShoppingItem.query.filter_by(is_purchased=False).order_by(ShoppingItem.added_at.desc()).all()

    return {
        "stats": {
            "total_items": len(dicts),
            "expiring": len(expiring),
            "expired": len(expired),
            "fresh": len(fresh),
            "inventory_value": inventory_value(items),
            "unread_notifications": unread_count(),
            "shopping_pending": len(shopping),
        },
        "attention": attention,
        "recipe_suggestions": suggestions,
        "shopping_preview": [s.to_dict() for s in shopping[:5]],
        "activity": activity_series(14),
        "categories": category_breakdown(items),
    }


# --------------------------------------------------------------------------
# Analytics page
# --------------------------------------------------------------------------
def analytics_overview(days=30):
    today = date.today()
    start = datetime.combine(today - timedelta(days=days - 1), time.min)

    consumed = ConsumptionLog.query.filter(ConsumptionLog.consumed_at >= start).all()
    wasted = WasteLog.query.filter(WasteLog.wasted_at >= start).all()
    items = active_items()

    consumed_cost = round(sum(c.cost for c in consumed), 2)
    waste_cost = round(sum(w.cost for w in wasted), 2)
    if consumed_cost + waste_cost > 0:
        waste_rate = round(100 * waste_cost / (consumed_cost + waste_cost))
    elif consumed or wasted:
        waste_rate = round(100 * len(wasted) / (len(consumed) + len(wasted)))
    else:
        waste_rate = 0

    waste_by_cat = defaultdict(lambda: {"cost": 0.0, "count": 0})
    for w in wasted:
        name = w.category.name if w.category else "Other"
        waste_by_cat[name]["cost"] += w.cost
        waste_by_cat[name]["count"] += 1
    waste_by_category = sorted(
        ({"name": n, "cost": round(v["cost"], 2), "count": v["count"]} for n, v in waste_by_cat.items()),
        key=lambda x: (-x["cost"], -x["count"]),
    )

    reasons = Counter(w.reason or "other" for w in wasted)

    by_item = defaultdict(lambda: {"cost": 0.0, "count": 0})
    for w in wasted:
        by_item[w.item_name]["cost"] += w.cost
        by_item[w.item_name]["count"] += 1
    top_wasted = sorted(
        ({"name": n, "cost": round(v["cost"], 2), "count": v["count"]} for n, v in by_item.items()),
        key=lambda x: (-x["cost"], -x["count"]),
    )[:5]

    top_consumed_counter = Counter()
    for c in consumed:
        top_consumed_counter[c.item_name] += 1
    top_consumed = [{"name": n, "count": c} for n, c in top_consumed_counter.most_common(5)]

    # Plain-language tips based on the numbers above.
    expired_now = sum(1 for i in items if i.days_left() is not None and i.days_left() < 0)
    soon_now = sum(
        1 for i in items
        if i.days_left() is not None and 0 <= i.days_left() <= current_app.config.get("EXPIRING_SOON_DAYS", 3)
    )
    insights = []
    if expired_now:
        insights.append(f"{expired_now} item(s) in your fridge have already expired - remove them or log them as waste.")
    if soon_now:
        insights.append(f"{soon_now} item(s) expire soon. Open Recipes and cook something that uses them.")
    if waste_by_category:
        top = waste_by_category[0]
        insights.append(f"{top['name']} is your most wasted category in this period. Buy smaller amounts next time.")
    if waste_rate >= 30:
        insights.append(f"About {waste_rate}% of what you bought went to waste. Try planning meals before shopping.")
    if consumed and waste_rate < 15:
        insights.append("Nice work - very little of your food is going to waste.")
    if not insights:
        insights.append("Add items and log what you use or throw away to see tips here.")

    return {
        "days": days,
        "kpis": {
            "consumed_count": len(consumed),
            "wasted_count": len(wasted),
            "consumed_cost": consumed_cost,
            "waste_cost": waste_cost,
            "waste_rate": waste_rate,
            "inventory_value": inventory_value(items),
            "active_items": len(items),
        },
        "activity": activity_series(days),
        "inventory_by_category": category_breakdown(items),
        "waste_by_category": waste_by_category,
        "waste_reasons": [{"reason": r, "count": c} for r, c in reasons.most_common()],
        "top_wasted": top_wasted,
        "top_consumed": top_consumed,
        "insights": insights,
    }


def categories_by_name():
    return {c.name: c for c in Category.query.all()}
