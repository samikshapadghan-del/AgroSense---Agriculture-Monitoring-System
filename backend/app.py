"""Flask application for the AgroSense smart agriculture dashboard."""

from __future__ import annotations

import os
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

try:
    from .services import (
        ServiceError,
        analyze_crop,
        build_dashboard,
        disease_risk,
        get_weather,
        irrigation_advice,
        market_prediction,
        reverse_geocode,
    )
except ImportError:  # Allows `python backend/app.py` from the project root.
    from services import (  # type: ignore
        ServiceError,
        analyze_crop,
        build_dashboard,
        disease_risk,
        get_weather,
        irrigation_advice,
        market_prediction,
        reverse_geocode,
    )

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"


def create_app(testing: bool = False) -> Flask:
    app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")
    app.config.update(TESTING=testing, JSON_SORT_KEYS=False)
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok", "service": "AgroSense API", "version": "2.0.0"})

    @app.get("/api/crops")
    def crops():
        return jsonify(
            {
                "crops": [
                    "Wheat",
                    "Rice",
                    "Cotton",
                    "Soybean",
                    "Maize",
                    "Tomato",
                    "Onion",
                    "Potato",
                ]
            }
        )

    @app.post("/api/crop-analysis")
    def crop_analysis_api():
        return jsonify(analyze_crop(_json_body()))

    @app.post("/api/irrigation-advice")
    def irrigation_api():
        return jsonify(irrigation_advice(_json_body()))

    @app.post("/api/disease-risk")
    def disease_api():
        return jsonify(disease_risk(_json_body()))

    @app.post("/api/market-price")
    def market_api():
        return jsonify(market_prediction(_json_body()))

    @app.get("/api/weather")
    def weather_api():
        return jsonify(get_weather(request.args.get("lat"), request.args.get("lon")))

    @app.get("/api/location")
    def location_api():
        return jsonify(reverse_geocode(request.args.get("lat"), request.args.get("lon")))

    @app.post("/api/analyze")
    def analyze_api():
        return jsonify(build_dashboard(_json_body()))

    @app.errorhandler(ServiceError)
    def handle_service_error(error: ServiceError):
        return jsonify({"error": error.message, "fields": error.fields}), error.status_code

    @app.errorhandler(404)
    def not_found(_error):
        if request.path.startswith("/api/"):
            return jsonify({"error": "API endpoint not found"}), 404
        return send_from_directory(FRONTEND_DIR, "index.html")

    @app.errorhandler(Exception)
    def unhandled_error(error: Exception):
        if app.testing:
            raise error
        app.logger.exception("Unhandled API error")
        return jsonify({"error": "Unexpected server error"}), 500

    @app.get("/")
    def index():
        return send_from_directory(FRONTEND_DIR, "index.html")

    @app.get("/<path:path>")
    def static_files(path: str):
        requested = FRONTEND_DIR / path
        if requested.is_file():
            return send_from_directory(FRONTEND_DIR, path)
        return send_from_directory(FRONTEND_DIR, "index.html")

    return app


def _json_body() -> dict:
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ServiceError("Request body must be a JSON object", 400)
    return body


app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "1") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
