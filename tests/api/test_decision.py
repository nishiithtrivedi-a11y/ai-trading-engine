from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)

def test_decision_latest_endpoint():
    response = client.get("/api/v1/decision/latest")
    assert response.status_code == 200
    data = response.json()
    assert "summary_markdown" in data
    assert "portfolio_plan" in data
