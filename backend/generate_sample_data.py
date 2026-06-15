"""Generate a deterministic demo dataset for testing the ML training pipeline."""

from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
OUTPUT = BASE / "data" / "crop_market_data.csv"
BASE_PRICES = {
    "Wheat": 2425,
    "Rice": 2320,
    "Cotton": 7520,
    "Soybean": 4890,
    "Maize": 2280,
    "Tomato": 1950,
    "Onion": 1720,
    "Potato": 1550,
}


def main() -> None:
    rng = np.random.default_rng(42)
    rows = []
    for crop, base in BASE_PRICES.items():
        for _ in range(55):
            soil = rng.uniform(25, 85)
            ndvi = rng.uniform(0.3, 0.9)
            humidity = rng.uniform(30, 90)
            temperature = rng.uniform(18, 39)
            rainfall = rng.uniform(0, 45)
            quality = np.clip(25 + ndvi * 70 - abs(soil - 55) * 0.35 + rng.normal(0, 6), 20, 98)
            health = np.clip(30 + ndvi * 65 - abs(humidity - 60) * 0.25 + rng.normal(0, 5), 20, 98)
            price = base * (0.60 + quality / 100 * 0.58) * (0.90 + health / 100 * 0.15) + rng.normal(0, base * 0.035)
            rows.append(
                {
                    "crop": crop,
                    "soil_moisture": round(soil, 2),
                    "ndvi": round(ndvi, 3),
                    "humidity": round(humidity, 2),
                    "temperature": round(temperature, 2),
                    "rainfall": round(rainfall, 2),
                    "quality_score": round(quality, 2),
                    "health_score": round(health, 2),
                    "base_price": base,
                    "market_price": round(max(100, price), 2),
                }
            )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUTPUT, index=False)
    print(f"Generated {len(rows)} rows at {OUTPUT}")


if __name__ == "__main__":
    main()
