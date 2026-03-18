from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)

def test_paper_state_endpoint():
    response = client.get("/api/v1/paper/state")
    assert response.status_code == 200
    data = response.json()
    assert "summary_markdown" in data
    assert "journal" in data
    assert isinstance(data["journal"], list)
