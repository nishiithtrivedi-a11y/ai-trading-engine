from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)

def test_derivatives_summary_endpoint():
    response = client.get("/api/v1/derivatives/summary")
    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"

def test_derivatives_chain_endpoint():
    response = client.get("/api/v1/derivatives/chain?symbol=NIFTY")
    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"
