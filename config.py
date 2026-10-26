"""Application settings. You can override any of these with environment variables."""
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-before-deploying")

    # The SQLite database file lives in the "instance" folder.
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///" + os.path.join(BASE_DIR, "instance", "fridge.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Items that expire within this many days count as "expiring soon".
    EXPIRING_SOON_DAYS = int(os.environ.get("EXPIRING_SOON_DAYS", "3"))

    # On the very first run, add sample food + history so every page has something to show.
    # Set SEED_DEMO_ITEMS=0 to start with an empty fridge.
    SEED_DEMO_ITEMS = os.environ.get("SEED_DEMO_ITEMS", "1") == "1"

    # Symbol shown next to prices.
    CURRENCY_SYMBOL = os.environ.get("CURRENCY_SYMBOL", "₹")
