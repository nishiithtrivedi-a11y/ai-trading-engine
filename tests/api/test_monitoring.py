from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)

def test_monitoring_latest_endpoint():
    response = client.get("/api/v1/monitoring/latest")
    assert response.status_code == 200
    data = response.json()
    assert "regime" in data
    assert "alerts" in data
    assert isinstance(data["alerts"], list)
