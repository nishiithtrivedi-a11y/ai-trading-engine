"""
API-level tests for the provider sessions router.

Tests HTTP layer: status codes, response shapes, credential masking
at the API boundary, and behavior for unknown providers.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)


def test_get_all_sessions_returns_providers() -> None:
    resp = client.get("/api/v1/providers/sessions")
    assert resp.status_code == 200
    body = resp.json()
    assert "providers" in body
    providers = body["providers"]
    assert len(providers) == 3  # Zerodha, Dhan, Upstox
    types = {p["provider_type"] for p in providers}
    assert "zerodha" in types
    assert "dhan" in types
    assert "upstox" in types


def test_get_single_session_known_provider() -> None:
    resp = client.get("/api/v1/providers/sessions/zerodha")
    assert resp.status_code == 200
    body = resp.json()
    assert "provider" in body
    assert body["provider"]["provider_type"] == "zerodha"


def test_get_single_session_unknown_returns_400() -> None:
    resp = client.get("/api/v1/providers/sessions/some_unknown_broker")
    assert resp.status_code == 400


def test_validate_session_known_provider() -> None:
    resp = client.post("/api/v1/providers/sessions/dhan/validate")
    assert resp.status_code == 200
    body = resp.json()
    assert "provider" in body
    provider = body["provider"]
    # All masked_indicator values must be "Not Set" or masked (contain bullets)
    for key, val in provider.get("masked_indicators", {}).items():
        assert val == "Not Set" or "•" in val, (
            f"Unmasked credential indicator for {key}: {val}"
        )


def test_validate_session_unknown_returns_400() -> None:
    resp = client.post("/api/v1/providers/sessions/fake_broker/validate")
    assert resp.status_code == 400


def test_configure_credential_response_masks_value() -> None:
    """Credential value sent in must never appear in response."""
    secret_value = "super_secret_api_key_12345"
    resp = client.post("/api/v1/providers/sessions/zerodha/configure", json={
        "credential_name": "API_KEY",
        "value": secret_value,
    })
    assert resp.status_code == 200
    # The raw secret must not appear in the response body
    assert secret_value not in resp.text


def test_configure_unknown_credential_type() -> None:
    """Configuring an unrecognized credential name should return an error state, not 500."""
    resp = client.post("/api/v1/providers/sessions/zerodha/configure", json={
        "credential_name": "NONEXISTENT_FIELD",
        "value": "some_val",
    })
    assert resp.status_code == 200  # returns error state in body, not HTTP 500
    body = resp.json()
    assert body["provider"]["session_status"] == "error"


def test_configure_multiple_dhan_credentials_uses_dhan_provider_id() -> None:
    resp = client.post(
        "/api/v1/providers/sessions/dhan/credentials",
        json={"credentials": {"CLIENT_ID": "demo_client", "ACCESS_TOKEN": "demo_token"}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"]["provider_type"] == "dhan"
    assert "demo_client" not in resp.text
    assert "demo_token" not in resp.text
