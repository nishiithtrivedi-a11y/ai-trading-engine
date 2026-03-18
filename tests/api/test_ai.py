from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)

def test_ai_status_endpoint():
    response = client.get("/api/v1/ai/status")
    assert response.status_code == 200
    assert response.json()["mode"] == "local_placeholder"

def test_ai_prompt_endpoint():
    response = client.post("/api/v1/ai/prompt", json={
        "prompt": "Analyze AAPL",
        "context_sources": ["scanner"]
    })
    assert response.status_code == 200
    assert "local placeholder" in response.json()["response"]
