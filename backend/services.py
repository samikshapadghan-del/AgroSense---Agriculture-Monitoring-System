"""Domain services used by the AgroSense Flask API."""

from __future__ import annotations

import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
import requests

BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_PATH = Path(os.getenv("AGROSENSE_MODEL_PATH", BASE_DIR / "models" / "market_model.joblib"))

CROP_PROFILES = {
    "Wheat": {"base_price": 2425, "optimal_moisture": (40, 65), "kc": 0.85},
    "Rice": {"base_price": 2320, "optimal_moisture": (60, 85), "kc": 1.15},
    "Cotton": {"base_price": 7520, "optimal_moisture": (45, 65), "kc": 0.90},
    "Soybean": {"base_price": 4890, "optimal_moisture": (45, 70), "kc": 0.95},
    "Maize": {"base_price": 2280, "optimal_moisture": (40, 68), "kc": 1.00},
    "Tomato": {"base_price": 1950, "optimal_moisture": (55, 75), "kc": 1.10},
    "Onion": {"base_price": 1720, "optimal_moisture": (45, 65), "kc": 0.90},
    "Potato": {"base_price": 1550, "optimal_moisture": (50, 70), "kc": 1.05},
}

_model_cache: dict[str, Any] = {"mtime": None, "artifact": None}


class ServiceError(Exception):
    def __init__(self, message: str, status_code: int = 400, fields: dict | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.fields = fields or {}


def _number(data: dict, key: str, minimum: float, maximum: float, default: float | None = None) -> float:
    raw = data.get(key, default)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise ServiceError("Invalid sensor data", fields={key: "Must be a number"}) from None
    if not math.isfinite(value) or value < minimum or value > maximum:
        raise ServiceError(
            "Sensor data is outside the supported range",
            fields={key: f"Must be between {minimum:g} and {maximum:g}"},
        )
    return value


def _crop(data: dict) -> str:
    supplied = str(data.get("crop", "Wheat")).strip().title()
    if supplied not in CROP_PROFILES:
        raise ServiceError("Unsupported crop", fields={"crop": f"Choose one of: {', '.join(CROP_PROFILES)}"})
    return supplied


def _inputs(data: dict) -> dict[str, float | str]:
    return {
        "crop": _crop(data),
        "soil_moisture": _number(data, "soilMoisture", 0, 100, 45),
        "ndvi": _number(data, "ndvi", 0, 1, 0.6),
        "humidity": _number(data, "humidity", 0, 100, 60),
        "temperature": _number(data, "temperature", -10, 60, 28),
        "rainfall": _number(data, "rainfall", 0, 500, 0),
        "quality_score": _number(data, "qualityScore", 0, 100, 70),
    }


def _range_score(value: float, low: float, high: float, tolerance: float) -> float:
    if low <= value <= high:
        return 100.0
    distance = low - value if value < low else value - high
    return max(0.0, 100.0 - (distance / tolerance) * 100.0)


def analyze_crop(data: dict) -> dict:
    values = _inputs(data)
    crop = str(values["crop"])
    soil = float(values["soil_moisture"])
    ndvi = float(values["ndvi"])
    humidity = float(values["humidity"])
    temperature = float(values["temperature"])
    profile = CROP_PROFILES[crop]

    moisture_score = _range_score(soil, *profile["optimal_moisture"], tolerance=35)
    vegetation_score = min(100.0, max(0.0, ndvi * 115))
    humidity_score = _range_score(humidity, 40, 72, tolerance=35)
    temperature_score = _range_score(temperature, 18, 32, tolerance=18)
    score = round(
        moisture_score * 0.30
        + vegetation_score * 0.40
        + humidity_score * 0.15
        + temperature_score * 0.15
    )

    if score >= 85:
        status, label = "excellent", "Excellent"
    elif score >= 70:
        status, label = "good", "Good"
    elif score >= 55:
        status, label = "watch", "Needs attention"
    elif score >= 35:
        status, label = "poor", "Stressed"
    else:
        status, label = "critical", "Critical"

    observations = []
    if soil < profile["optimal_moisture"][0]:
        observations.append("Soil moisture is below the preferred range for this crop.")
    elif soil > profile["optimal_moisture"][1]:
        observations.append("The root zone is wetter than the preferred range.")
    if ndvi < 0.45:
        observations.append("Low NDVI suggests sparse canopy, nutrient stress, pests, or disease.")
    elif ndvi >= 0.72:
        observations.append("NDVI indicates a dense and vigorous crop canopy.")
    if temperature > 35:
        observations.append("Heat stress may reduce growth during the hottest part of the day.")
    if not observations:
        observations.append("Sensor values are within generally healthy operating ranges.")

    return {
        "score": score,
        "status": status,
        "label": label,
        "summary": f"{crop} health is {label.lower()} with a score of {score}/100.",
        "componentScores": {
            "moisture": round(moisture_score),
            "vegetation": round(vegetation_score),
            "humidity": round(humidity_score),
            "temperature": round(temperature_score),
        },
        "observations": observations,
    }


def irrigation_advice(data: dict) -> dict:
    values = _inputs(data)
    crop = str(values["crop"])
    soil = float(values["soil_moisture"])
    temperature = float(values["temperature"])
    humidity = float(values["humidity"])
    rainfall = float(values["rainfall"])
    low, high = CROP_PROFILES[crop]["optimal_moisture"]

    deficit = max(0.0, low - soil)
    heat_factor = 1.18 if temperature >= 34 else 1.0
    dry_air_factor = 1.12 if humidity < 35 else 1.0
    rain_offset = min(1.0, rainfall / 18.0)
    liters_per_m2 = max(0.0, deficit * 0.42 * heat_factor * dry_air_factor * (1 - rain_offset))

    if rainfall >= 20 or soil > high:
        priority, action, liters_per_m2 = "low", "Pause irrigation", 0.0
        reason = "Rainfall or root-zone moisture is already sufficient. Check drainage before watering again."
    elif soil < low - 12:
        priority, action = "urgent", "Irrigate now"
        reason = "The root zone is substantially below the crop's preferred moisture range."
    elif soil < low:
        priority, action = "medium", "Irrigate soon"
        reason = "A moderate moisture deficit is present. Water in the early morning or evening."
    else:
        priority, action, liters_per_m2 = "low", "Maintain schedule", 0.0
        reason = "Soil moisture is currently in the preferred range."

    duration = round(liters_per_m2 / 0.55) if liters_per_m2 else 0
    return {
        "priority": priority,
        "action": action,
        "recommendedLitersPerM2": round(liters_per_m2, 1),
        "estimatedDripMinutes": duration,
        "reason": reason,
        "nextCheckHours": 6 if priority == "urgent" else 12 if priority == "medium" else 24,
    }


def disease_risk(data: dict) -> dict:
    values = _inputs(data)
    humidity = float(values["humidity"])
    temperature = float(values["temperature"])
    soil = float(values["soil_moisture"])
    ndvi = float(values["ndvi"])
    rainfall = float(values["rainfall"])

    score = 8.0
    score += max(0, humidity - 60) * 1.15
    score += max(0, soil - 68) * 0.75
    score += min(rainfall, 45) * 0.55
    score += 18 if 20 <= temperature <= 30 and humidity >= 75 else 0
    score += 16 if ndvi < 0.42 else 7 if ndvi < 0.58 else 0
    score = round(min(100, score))

    level = "High" if score >= 65 else "Moderate" if score >= 35 else "Low"
    factors = []
    if humidity >= 75:
        factors.append("prolonged high humidity")
    if soil >= 75:
        factors.append("waterlogged root zone")
    if rainfall >= 15:
        factors.append("recent or forecast rainfall")
    if ndvi < 0.45:
        factors.append("weak vegetation signal")
    if not factors:
        factors.append("no major environmental triggers detected")

    actions = (
        ["Inspect lower leaves today", "Avoid overhead or night irrigation", "Improve canopy airflow"]
        if level == "High"
        else ["Scout twice this week", "Keep foliage dry overnight"]
        if level == "Moderate"
        else ["Continue weekly scouting", "Keep tools and field edges clean"]
    )
    return {"score": score, "level": level, "factors": factors, "actions": actions}


def _load_model():
    if not MODEL_PATH.exists():
        return None
    mtime = MODEL_PATH.stat().st_mtime
    if _model_cache["mtime"] != mtime:
        _model_cache["artifact"] = joblib.load(MODEL_PATH)
        _model_cache["mtime"] = mtime
    return _model_cache["artifact"]


def market_prediction(data: dict) -> dict:
    values = _inputs(data)
    crop = str(values["crop"])
    base_price = float(CROP_PROFILES[crop]["base_price"])
    health_score = analyze_crop(data)["score"]
    quality_score = float(values["quality_score"])
    feature_row = {
        "crop": crop,
        "soil_moisture": float(values["soil_moisture"]),
        "ndvi": float(values["ndvi"]),
        "humidity": float(values["humidity"]),
        "temperature": float(values["temperature"]),
        "rainfall": float(values["rainfall"]),
        "quality_score": quality_score,
        "health_score": health_score,
        "base_price": base_price,
    }

    model_used = False
    model_name = "AgroSense quality estimator"
    artifact = _load_model()
    try:
        if artifact:
            model = artifact.get("model", artifact) if isinstance(artifact, dict) else artifact
            predicted = float(model.predict(pd.DataFrame([feature_row]))[0])
            model_used = True
            if isinstance(artifact, dict):
                model_name = artifact.get("model_name", "Trained Kaggle model")
        else:
            raise ValueError("No trained model")
    except Exception:
        quality_factor = 0.62 + quality_score / 100 * 0.56
        health_factor = 0.88 + health_score / 100 * 0.18
        moisture_factor = 1 - min(abs(55 - float(values["soil_moisture"])) / 300, 0.14)
        predicted = base_price * quality_factor * health_factor * moisture_factor

    predicted = round(max(100, predicted), 2)
    low = round(predicted * 0.92, 2)
    high = round(predicted * 1.08, 2)
    grade = "Premium" if quality_score >= 82 else "Grade A" if quality_score >= 68 else "Standard" if quality_score >= 50 else "Below grade"
    confidence = "high" if model_used else "indicative"
    return {
        "crop": crop,
        "qualityGrade": grade,
        "qualityScore": round(quality_score),
        "estimatedPrice": predicted,
        "priceRange": {"low": low, "high": high},
        "currency": "INR",
        "unit": "quintal",
        "modelUsed": model_used,
        "modelName": model_name,
        "confidence": confidence,
        "advice": "Clean, grade, and compare nearby mandi prices before sale." if quality_score >= 60 else "Improve sorting and minimize storage losses before sale.",
    }


def _coordinates(lat: Any, lon: Any) -> tuple[float, float]:
    try:
        latitude, longitude = float(lat), float(lon)
    except (TypeError, ValueError):
        raise ServiceError("Latitude and longitude are required", fields={"location": "Provide valid lat and lon"}) from None
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ServiceError("Invalid coordinates", fields={"location": "Coordinates are outside valid ranges"})
    return latitude, longitude


def get_weather(lat: Any, lon: Any) -> dict:
    latitude, longitude = _coordinates(lat, lon)
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max",
        "forecast_days": 7,
        "timezone": "auto",
    }
    try:
        response = requests.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=8)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as error:
        raise ServiceError("Weather provider is temporarily unavailable", 503) from error

    current = payload.get("current", {})
    daily = payload.get("daily", {})
    rain_values = daily.get("precipitation_sum", [])
    forecast = []
    for index, date in enumerate(daily.get("time", [])):
        forecast.append(
            {
                "date": date,
                "max": _at(daily.get("temperature_2m_max", []), index),
                "min": _at(daily.get("temperature_2m_min", []), index),
                "rain": _at(rain_values, index),
                "rainProbability": _at(daily.get("precipitation_probability_max", []), index),
            }
        )
    return {
        "source": "Open-Meteo",
        "timezone": payload.get("timezone"),
        "current": {
            "temperature": current.get("temperature_2m"),
            "humidity": current.get("relative_humidity_2m"),
            "precipitation": current.get("precipitation"),
            "windSpeed": current.get("wind_speed_10m"),
            "weatherCode": current.get("weather_code"),
        },
        "rainNext3Days": round(sum(float(v or 0) for v in rain_values[:3]), 1),
        "forecast": forecast,
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
    }


def reverse_geocode(lat: Any, lon: Any) -> dict:
    latitude, longitude = _coordinates(lat, lon)
    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": latitude, "lon": longitude, "format": "jsonv2", "zoom": 12},
            headers={"User-Agent": "AgroSense/2.0 educational-smart-farming-app"},
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as error:
        raise ServiceError("Location lookup is temporarily unavailable", 503) from error
    address = payload.get("address", {})
    locality = address.get("village") or address.get("town") or address.get("city") or address.get("county")
    region = address.get("state") or address.get("region")
    country = address.get("country")
    label = ", ".join(part for part in (locality, region, country) if part) or payload.get("display_name", "Detected farm")
    return {
        "latitude": latitude,
        "longitude": longitude,
        "label": label,
        "locality": locality,
        "region": region,
        "country": country,
        "provider": "OpenStreetMap Nominatim",
    }


def _at(values: list, index: int):
    return values[index] if index < len(values) else None


def build_dashboard(data: dict) -> dict:
    analysis = analyze_crop(data)
    irrigation = irrigation_advice(data)
    disease = disease_risk(data)
    market = market_prediction(data)
    weather = None
    weather_error = None
    lat, lon = data.get("lat"), data.get("lon")
    if lat is not None and lon is not None:
        try:
            weather = get_weather(lat, lon)
        except ServiceError as error:
            weather_error = error.message

    checklist = []
    if irrigation["priority"] in {"urgent", "medium"}:
        checklist.append(irrigation["action"])
    checklist.extend(disease["actions"][:2])
    if analysis["componentScores"]["vegetation"] < 60:
        checklist.append("Inspect crop canopy and verify nutrient or pest stress")
    if not checklist:
        checklist.append("Record sensor readings and continue routine field scouting")

    return {
        "analysis": analysis,
        "irrigation": irrigation,
        "disease": disease,
        "market": market,
        "weather": weather,
        "weatherError": weather_error,
        "checklist": checklist,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }
