# AgroSense Full-Stack Smart Agriculture Monitoring System

AgroSense is a responsive Flask and JavaScript dashboard that converts farm sensor readings, GPS weather, crop health, and quality data into practical field recommendations and market-price estimates.

## Features

- Animated responsive green dashboard with glass panels and moving metric cards
- Persisted dark and light themes
- Crop health score from soil moisture, NDVI, humidity, and temperature
- Crop-specific irrigation quantity and timing advice
- Environmental disease-risk score with scouting actions
- Browser GPS detection and reverse-geocoded farm location
- Seven-day live weather forecast from Open-Meteo
- Market price prediction based on crop type, quality, and field condition
- Random Forest training pipeline for common Kaggle commodity-price datasets
- Demo dataset generator, automated API tests, and offline estimate fallback

## Project Structure

```text
agrosense_fullstack/
|-- backend/
|   |-- __init__.py
|   |-- app.py                  # Flask routes and static frontend hosting
|   |-- services.py             # Crop, irrigation, disease, weather, and market logic
|   |-- train_model.py          # Kaggle CSV cleaning and ML training pipeline
|   `-- generate_sample_data.py # Reproducible demo training data
|-- data/
|   |-- README.md
|   `-- crop_market_data.csv    # Generated demo or downloaded Kaggle data
|-- frontend/
|   |-- index.html
|   |-- style.css
|   `-- script.js
|-- models/
|   |-- market_model.joblib     # Created by the training command
|   `-- metrics.json
|-- tests/
|   `-- test_api.py
|-- .env.example
|-- .gitignore
|-- requirements.txt
`-- README.md
```

## Quick Start

Python 3.10 or newer is recommended.

### Windows PowerShell

```powershell
cd "AgroSense_FullStack\agrosense_fullstack"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python backend\generate_sample_data.py
python backend\train_model.py
python backend\app.py
```

### macOS or Linux

```bash
cd AgroSense_FullStack/agrosense_fullstack
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python backend/generate_sample_data.py
python backend/train_model.py
python backend/app.py
```

Open `http://127.0.0.1:5000`. Do not open `frontend/index.html` directly because the dashboard calls Flask API routes.

The app still returns a deterministic market estimate when no trained model exists. Running the two ML commands makes the market card use the trained model.

## GPS and Weather

1. Start Flask and open the app through `http://127.0.0.1:5000` or `http://localhost:5000`.
2. Select **Detect** in the Farm location card.
3. Allow location permission in the browser.
4. AgroSense reverse geocodes the coordinates with OpenStreetMap Nominatim and retrieves weather from Open-Meteo.

Internet access is needed only for GPS place names and live weather. All crop, irrigation, disease, and fallback price calculations run locally.

## API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | Backend status |
| GET | `/api/crops` | Supported crop names |
| POST | `/api/crop-analysis` | Crop health score and observations |
| POST | `/api/irrigation-advice` | Irrigation quantity, timing, and priority |
| POST | `/api/disease-risk` | Disease risk, factors, and actions |
| POST | `/api/market-price` | Quality-aware market price prediction |
| GET | `/api/location?lat=...&lon=...` | Reverse-geocoded farm location |
| GET | `/api/weather?lat=...&lon=...` | Current weather and seven-day forecast |
| POST | `/api/analyze` | Aggregate response used by the dashboard |

Example request:

```bash
curl -X POST http://127.0.0.1:5000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"crop":"Wheat","soilMoisture":52,"ndvi":0.72,"humidity":61,"temperature":28,"rainfall":4,"qualityScore":82}'
```

## Train with a Kaggle Dataset

Download a crop price, commodity price, or mandi price CSV from Kaggle and place it in `data/`. The trainer recognizes common names such as:

- Crop: `crop`, `commodity`, `crop_name`, `commodity_name`
- Target price: `market_price`, `modal_price`, `price`, `avg_price`, `selling_price`
- Optional features: soil moisture, NDVI, humidity, temperature, rainfall, quality, health, base price, or MSP

Inspect the available columns:

```powershell
python backend\train_model.py --dataset data\your_kaggle_file.csv --show-columns
```

Train with automatic column detection:

```powershell
python backend\train_model.py --dataset data\your_kaggle_file.csv
```

Specify a nonstandard price target:

```powershell
python backend\train_model.py --dataset data\your_kaggle_file.csv --target modal_price_rs
```

The command writes `models/market_model.joblib` and evaluation details to `models/metrics.json`. For datasets without sensor columns, the trainer fills documented neutral defaults; a dataset containing crop quality and environmental features will produce a more meaningful model.

## Tests

```powershell
pytest -q
```

## Configuration

- `PORT`: Flask port, default `5000`
- `FLASK_DEBUG`: `1` enables debug mode, default `1` when running `backend/app.py`
- `AGROSENSE_MODEL_PATH`: optional custom model artifact path

## Important Note

AgroSense is an educational decision-support project, not a replacement for field inspection, soil testing, official mandi prices, pesticide labels, or advice from local agricultural professionals.
