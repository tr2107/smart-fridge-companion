"""
app.py - the starting point of the Smart Fridge Companion.

Run it with:   python app.py
Then open:     http://127.0.0.1:5000
"""
import os

from flask import Flask, jsonify, render_template, request

from api import api
from config import Config
from models import db
from seed import seed_basics, seed_demo

# Each page: URL -> (template file, page id used to highlight the menu)
PAGES = {
    "/": ("dashboard.html", "dashboard"),
    "/inventory": ("inventory.html", "inventory"),
    "/add": ("add_item.html", "add"),
    "/recipes": ("recipes.html", "recipes"),
    "/shopping": ("shopping.html", "shopping"),
    "/analytics": ("analytics.html", "analytics"),
    "/notifications": ("notifications.html", "notifications"),
}


def create_app(config_overrides=None):
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(Config)
    if config_overrides:
        app.config.update(config_overrides)

    # Make sure the folder for the database file exists.
    os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), "instance"), exist_ok=True)

    db.init_app(app)
    app.register_blueprint(api)

    # One small function per page keeps things easy to follow.
    def make_page(template, page_id):
        def view():
            return render_template(template, page=page_id, currency=app.config["CURRENCY_SYMBOL"])
        view.__name__ = f"page_{page_id}"
        return view

    for url, (template, page_id) in PAGES.items():
        app.add_url_rule(url, view_func=make_page(template, page_id))

    # Always answer API mistakes with JSON (not an HTML error page).
    @app.errorhandler(404)
    def not_found(error):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Not found."}), 404
        return render_template("404.html", page="", currency=app.config["CURRENCY_SYMBOL"]), 404

    @app.errorhandler(405)
    def wrong_method(error):
        return jsonify({"error": "That method is not allowed here."}), 405

    @app.errorhandler(500)
    def server_error(error):
        db.session.rollback()
        return jsonify({"error": "Something went wrong on the server."}), 500

    with app.app_context():
        db.create_all()  # creates the tables the first time
        seed_basics()
        if app.config["SEED_DEMO_ITEMS"]:
            seed_demo()

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
