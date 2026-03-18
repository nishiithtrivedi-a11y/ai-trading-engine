from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)

def test_artifacts_runs_endpoint():
    response = client.get("/api/v1/artifacts/runs")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    
def test_artifacts_tree_endpoint_not_found():
    response = client.get("/api/v1/artifacts/tree?phase=nonexistent_phase")
    assert response.status_code == 404
