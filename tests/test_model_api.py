"""Automatic checks for the model API."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from services.model_api.main import app

client = TestClient(app)
HIGH = {"age": 67, "female": 1, "sbp": 152, "dbp": 84, "diabetes": 1,
        "told_high_bp": 1, "hba1c": 8.1, "bmi": 33, "hemoglobin": 11.9}
LOW = {"age": 32, "female": 0, "sbp": 115, "dbp": 72, "diabetes": 0,
       "told_high_bp": 0, "hba1c": 5.2, "bmi": 24, "hemoglobin": 15.1}


def test_health():
    assert client.get("/health").json()["status"] == "ok"


def test_high_risk_scores_above_low_risk():
    high = client.post("/score", json=HIGH).json()
    low = client.post("/score", json=LOW).json()
    assert high["risk"] > low["risk"]
    assert high["flag"] is True and low["flag"] is False


def test_reasons_only_use_real_values():
    drivers = client.post("/score", json=HIGH).json()["top_drivers"]
    assert len(drivers) >= 3
    assert all(d["value"] is not None for d in drivers)