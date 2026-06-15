from unittest.mock import patch

import pytest

from backend.app import create_app


@pytest.fixture()
def client():
    app = create_app(testing=True)
    return app.test_client()


def sample_payload():
    return {
        "crop": "Wheat",
        "soilMoisture": 55,
        "ndvi": 0.72,
        "humidity": 60,
        "temperature": 28,
        "rainfall": 3,
        "qualityScore": 82,
    }


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"


def test_dashboard_analysis_without_location(client):
    response = client.post("/api/analyze", json=sample_payload())
    assert response.status_code == 200
    body = response.get_json()
    assert 0 <= body["analysis"]["score"] <= 100
    assert body["irrigation"]["action"]
    assert body["disease"]["level"] in {"Low", "Moderate", "High"}
    assert body["market"]["estimatedPrice"] > 0
    assert body["weather"] is None


@pytest.mark.parametrize("endpoint", ["crop-analysis", "irrigation-advice", "disease-risk", "market-price"])
def test_dedicated_post_endpoints(client, endpoint):
    response = client.post(f"/api/{endpoint}", json=sample_payload())
    assert response.status_code == 200
    assert response.get_json()


def test_validation_error(client):
    payload = sample_payload()
    payload["ndvi"] = 4
    response = client.post("/api/crop-analysis", json=payload)
    assert response.status_code == 400
    assert "ndvi" in response.get_json()["fields"]


def test_weather_endpoint_with_mock(client):
    mock_payload = {
        "source": "Open-Meteo",
        "current": {"temperature": 27, "humidity": 61},
        "rainNext3Days": 5,
        "forecast": [],
    }
    with patch("backend.app.get_weather", return_value=mock_payload):
        response = client.get("/api/weather?lat=12.97&lon=77.59")
    assert response.status_code == 200
    assert response.get_json()["source"] == "Open-Meteo"


def test_frontend_is_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"AgroSense" in response.data
