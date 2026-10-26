"""
logic.py - pure helper functions (no database, no Flask).

Keeping the "thinking" code here makes it easy to understand and to test.
Everything in this file works on plain Python values.
"""
import re

# Units the app understands. Only g<->kg and ml<->l can be converted.
UNITS = ["pcs", "g", "kg", "ml", "l", "pack", "bottle"]

_CONVERSIONS = {
    "g": ("mass", 1.0),
    "kg": ("mass", 1000.0),
    "ml": ("volume", 1.0),
    "l": ("volume", 1000.0),
}

# Words ignored when comparing names ("Fresh Whole Milk" -> {"milk"}).
_STOP_WORDS = {
    "fresh", "whole", "organic", "raw", "ripe", "large", "small", "medium",
    "chopped", "diced", "sliced", "boneless", "of", "and", "the", "a", "frozen",
}


def convert(quantity, from_unit, to_unit):
    """Convert a quantity between units. Returns None if they are not compatible."""
    if from_unit == to_unit:
        return quantity
    a = _CONVERSIONS.get(from_unit)
    b = _CONVERSIONS.get(to_unit)
    if a and b and a[0] == b[0]:
        return quantity * a[1] / b[1]
    return None


def _singular(word):
    """Very small plural -> singular helper (tomatoes -> tomato, berries -> berry)."""
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith("oes"):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def name_tokens(name):
    """Turn a food name into a set of simple lowercase words."""
    words = re.findall(r"[a-z]+", (name or "").lower())
    return {_singular(w) for w in words if w not in _STOP_WORDS and len(w) > 1}


def names_match(a, b):
    """True if two food names refer to the same thing, e.g. 'egg' and 'Eggs (large)'."""
    ta, tb = name_tokens(a), name_tokens(b)
    if not ta or not tb:
        return False
    return ta <= tb or tb <= ta


def expiry_state(days_left, soon_days=3):
    """Return one of: none, expired, expiring, fresh."""
    if days_left is None:
        return "none"
    if days_left < 0:
        return "expired"
    if days_left <= soon_days:
        return "expiring"
    return "fresh"


def expiry_label(days_left):
    """Human friendly text for the number of days left."""
    if days_left is None:
        return "No expiry date"
    if days_left < -1:
        return f"Expired {-days_left} days ago"
    if days_left == -1:
        return "Expired yesterday"
    if days_left == 0:
        return "Expires today"
    if days_left == 1:
        return "Expires tomorrow"
    return f"Expires in {days_left} days"


def match_ingredients(ingredients, items):
    """
    Compare a recipe's ingredients with what is in the fridge.

    ingredients: list of {"name", "quantity", "unit"}
    items:       list of {"id", "name", "quantity", "unit", "days_left", "state"}

    Expired items are NOT used (you should not cook with them).
    If several items match, the one expiring first is chosen.
    """
    usable = [i for i in items if i["state"] != "expired" and i["quantity"] > 0]
    results = []
    for ing in ingredients:
        candidates = [i for i in usable if names_match(ing["name"], i["name"])]
        candidates.sort(
            key=lambda i: (i["days_left"] is None, i["days_left"] if i["days_left"] is not None else 0)
        )
        best = candidates[0] if candidates else None
        enough = None  # None means "cannot tell" (different units)
        if best:
            available = convert(best["quantity"], best["unit"], ing["unit"])
            if available is not None:
                enough = available + 1e-9 >= ing["quantity"]
        results.append({
            "name": ing["name"],
            "quantity": ing["quantity"],
            "unit": ing["unit"],
            "have": best is not None,
            "enough": enough,
            "item_id": best["id"] if best else None,
            "item_name": best["name"] if best else None,
            "item_state": best["state"] if best else None,
        })
    return results


def summarize_match(results):
    """Numbers used for sorting and showing recipe cards."""
    total = len(results)
    have = sum(1 for r in results if r["have"])
    expiring = sum(1 for r in results if r["item_state"] == "expiring")
    pct = round(100 * have / total) if total else 0
    return {
        "have_count": have,
        "total_count": total,
        "match_pct": pct,
        "expiring_used": expiring,
        "can_cook": total > 0 and have == total,
        # Recipes that rescue expiring food float to the top.
        "score": pct + 15 * expiring,
    }
