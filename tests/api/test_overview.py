from fastapi.testclient import TestClient
from src.api.main import app
import pytest
from unittest.mock import patch

client = TestClient(app)

def test_status_endpoint():
    response = client.get("/api/v1/status")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "message": "API is running"}

def test_overview_endpoint():
    """Test overview endpoint with standard output dir."""
    response = client.get("/api/v1/overview")
    # Even if output dir doesn't map perfectly, it shouldn't 500
    # It might return empty availability values
    assert response.status_code == 200
    data = response.json()
    assert "availability" in data
    assert "metrics" in data
    assert "market_state" in data
    assert "decision_summary" in data
