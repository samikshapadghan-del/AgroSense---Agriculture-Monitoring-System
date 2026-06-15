"""Train the AgroSense crop market-price model from a Kaggle-style CSV.

Examples:
    python backend/train_model.py --dataset data/crop_market_data.csv
    python backend/train_model.py --dataset data/my_kaggle_file.csv --target modal_price

The loader recognizes common Kaggle column names and derives missing sensor fields
when possible. Run with --show-columns to inspect a dataset before training.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATASET = BASE_DIR / "data" / "crop_market_data.csv"
DEFAULT_MODEL = BASE_DIR / "models" / "market_model.joblib"
DEFAULT_METRICS = BASE_DIR / "models" / "metrics.json"

FEATURES = [
    "crop",
    "soil_moisture",
    "ndvi",
    "humidity",
    "temperature",
    "rainfall",
    "quality_score",
    "health_score",
    "base_price",
]
NUMERIC_FEATURES = FEATURES[1:]

ALIASES = {
    "crop": ["crop", "commodity", "crop_name", "commodity_name", "item"],
    "market_price": ["market_price", "modal_price", "price", "avg_price", "average_price", "selling_price"],
    "soil_moisture": ["soil_moisture", "soilmoisture", "moisture", "soil_moisture_percent"],
    "ndvi": ["ndvi", "vegetation_index", "crop_health_index"],
    "humidity": ["humidity", "relative_humidity", "humidity_percent"],
    "temperature": ["temperature", "temp", "temperature_c", "avg_temperature"],
    "rainfall": ["rainfall", "rain", "precipitation", "rainfall_mm"],
    "quality_score": ["quality_score", "quality", "quality_index", "grade_score"],
    "health_score": ["health_score", "crop_health", "health_index"],
    "base_price": ["base_price", "minimum_support_price", "msp", "min_price", "minimum_price"],
}


def slug(value: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", value.strip().lower())).strip("_")


def rename_known_columns(frame: pd.DataFrame, explicit_target: str | None) -> pd.DataFrame:
    frame = frame.copy()
    normalized = {slug(column): column for column in frame.columns}
    rename_map = {}
    for canonical, options in ALIASES.items():
        for option in options:
            if option in normalized:
                rename_map[normalized[option]] = canonical
                break
    if explicit_target:
        target_slug = slug(explicit_target)
        if target_slug not in normalized:
            raise ValueError(f"Target column '{explicit_target}' was not found")
        rename_map[normalized[target_slug]] = "market_price"
    return frame.rename(columns=rename_map)


def numeric(series: pd.Series) -> pd.Series:
    if series.dtype == object:
        series = series.astype(str).str.replace(r"[^0-9.\-]", "", regex=True)
    return pd.to_numeric(series, errors="coerce")


def prepare_dataset(frame: pd.DataFrame, explicit_target: str | None) -> pd.DataFrame:
    frame = rename_known_columns(frame, explicit_target)
    if "crop" not in frame or "market_price" not in frame:
        raise ValueError("Dataset needs crop/commodity and price/modal_price columns")

    result = pd.DataFrame(index=frame.index)
    result["crop"] = frame["crop"].astype(str).str.strip().str.title()
    result["market_price"] = numeric(frame["market_price"])

    defaults = {
        "soil_moisture": 55.0,
        "ndvi": 0.62,
        "humidity": 60.0,
        "temperature": 28.0,
        "rainfall": 5.0,
        "quality_score": 70.0,
        "health_score": 70.0,
    }
    for column, default in defaults.items():
        result[column] = numeric(frame[column]) if column in frame else default

    if "base_price" in frame:
        result["base_price"] = numeric(frame["base_price"])
    else:
        result["base_price"] = result.groupby("crop")["market_price"].transform("median")

    # Normalize common 0-10 quality scales and 0-100 NDVI representations.
    if result["quality_score"].dropna().median() <= 10:
        result["quality_score"] *= 10
    if result["health_score"].dropna().median() <= 10:
        result["health_score"] *= 10
    if result["ndvi"].dropna().median() > 1:
        result["ndvi"] /= 100

    result = result.replace([np.inf, -np.inf], np.nan)
    result = result.dropna(subset=["crop", "market_price"])
    result = result[result["market_price"] > 0]
    result["ndvi"] = result["ndvi"].clip(0, 1)
    for column in ["soil_moisture", "humidity", "quality_score", "health_score"]:
        result[column] = result[column].clip(0, 100)
    if len(result) < 20:
        raise ValueError(f"Only {len(result)} usable rows found; at least 20 are required")
    return result


def train(dataset: Path, model_path: Path, metrics_path: Path, target: str | None) -> dict:
    raw = pd.read_csv(dataset)
    frame = prepare_dataset(raw, target)
    X = frame[FEATURES]
    y = frame["market_price"]

    preprocess = ColumnTransformer(
        [
            ("crop", OneHotEncoder(handle_unknown="ignore", sparse_output=False), ["crop"]),
            (
                "numbers",
                Pipeline([("imputer", SimpleImputer(strategy="median")), ("scale", StandardScaler())]),
                NUMERIC_FEATURES,
            ),
        ]
    )
    model = Pipeline(
        [
            ("preprocess", preprocess),
            (
                "regressor",
                RandomForestRegressor(
                    n_estimators=350,
                    min_samples_leaf=2,
                    random_state=42,
                    n_jobs=-1,
                ),
            ),
        ]
    )

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    model.fit(X_train, y_train)
    predictions = model.predict(X_test)
    metrics = {
        "rows": len(frame),
        "trainRows": len(X_train),
        "testRows": len(X_test),
        "mae": round(float(mean_absolute_error(y_test, predictions)), 2),
        "rmse": round(float(mean_squared_error(y_test, predictions) ** 0.5), 2),
        "r2": round(float(r2_score(y_test, predictions)), 4),
        "crops": sorted(frame["crop"].unique().tolist()),
        "trainedAt": datetime.now(timezone.utc).isoformat(),
        "dataset": str(dataset),
    }
    artifact = {
        "model": model,
        "model_name": "Random Forest crop quality price model",
        "features": FEATURES,
        "metrics": metrics,
    }
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, model_path)
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train the AgroSense market price model")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET, help="Path to a Kaggle CSV")
    parser.add_argument("--target", help="Price target column when auto-detection is not enough")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL, help="Output .joblib path")
    parser.add_argument("--metrics", type=Path, default=DEFAULT_METRICS, help="Output metrics JSON path")
    parser.add_argument("--show-columns", action="store_true", help="Print CSV columns and exit")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset = args.dataset.resolve()
    if not dataset.exists():
        raise FileNotFoundError(
            f"Dataset not found: {dataset}\n"
            "Download a Kaggle crop/commodity price CSV or use data/crop_market_data.csv."
        )
    if args.show_columns:
        print("\n".join(pd.read_csv(dataset, nrows=2).columns))
        return
    metrics = train(dataset, args.model.resolve(), args.metrics.resolve(), args.target)
    print(f"Model saved to: {args.model.resolve()}")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
