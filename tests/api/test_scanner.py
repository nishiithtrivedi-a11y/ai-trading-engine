from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)

def test_scanner_latest_endpoint():
    """Test scanner latest endpoint returns expected schema."""
    response = client.get("/api/v1/scanner/latest")
    assert response.status_code == 200
    data = response.json()
    assert "metadata" in data
    assert "opportunities" in data
    
    # Opportunities should be a list, metadata a dict
    assert isinstance(data["metadata"], dict)
    assert isinstance(data["opportunities"], list)
