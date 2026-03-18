from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)

def test_providers_health_endpoint():
    response = client.get("/api/v1/providers/health")
    assert response.status_code == 200
    data = response.json()
    assert "diagnostics" in data
    assert "default_provider" in data
    assert isinstance(data["diagnostics"], list)
