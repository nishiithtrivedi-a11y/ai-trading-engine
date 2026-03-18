from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)

def test_logs_validation_endpoint():
    response = client.get("/api/v1/logs/validation")
    assert response.status_code == 200
    data = response.json()
    assert "overall_status" in data
    assert "subsystems" in data

def test_logs_runner_endpoint():
    response = client.get("/api/v1/logs/runner")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
