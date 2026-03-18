from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)

def test_profiles_endpoint():
    response = client.get("/api/v1/profiles/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    if len(data) > 0:
        assert "id" in data[0]
        assert "enabled_families" in data[0]
