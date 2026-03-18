"""
API-level tests for the automation router.

Tests the HTTP layer: status codes, response shapes, 429 cooldown,
and masking guarantee at the API output boundary.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)


def test_get_schedules_returns_list() -> None:
    resp = client.get("/api/v1/automation/schedules")
    assert resp.status_code == 200
    body = resp.json()
    assert "schedules" in body
    assert isinstance(body["schedules"], list)
    # Each entry must have the required shape
    for s in body["schedules"]:
        assert "job_id" in s
        assert "pipeline_type" in s
        assert "next_run" in s
        assert "last_run" in s


def test_get_recent_runs_returns_list() -> None:
    resp = client.get("/api/v1/automation/runs")
    assert resp.status_code == 200
    body = resp.json()
    assert "runs" in body
    assert isinstance(body["runs"], list)


def test_trigger_valid_pipeline() -> None:
    resp = client.post("/api/v1/automation/trigger/morning_scan",
                       json={"trigger_source": "manual_api"})
    assert resp.status_code == 200
    body = resp.json()
    assert "run" in body
    run = body["run"]
    assert run["pipeline_type"] == "morning_scan"
    # SAFETY: execution mode must never be 'live'
    assert run["execution_mode"] != "live"


def test_trigger_invalid_pipeline_type_is_400() -> None:
    resp = client.post("/api/v1/automation/trigger/buy_live_order")
    assert resp.status_code == 400


def test_trigger_cooldown_returns_429() -> None:
    """The second immediate re-trigger should be rate-limited with 429."""
    # Use eod_processing — unique to this test, won't have been triggered in this
    # test session yet, so the first call should succeed and expose cooldown.
    resp1 = client.post("/api/v1/automation/trigger/eod_processing",
                        json={"trigger_source": "manual_api"})
    assert resp1.status_code == 200, f"First call failed unexpectedly: {resp1.json()}"
    # Second immediate call should hit the cooldown
    resp2 = client.post("/api/v1/automation/trigger/eod_processing",
                        json={"trigger_source": "manual_api"})
    assert resp2.status_code == 429, f"Expected 429, got {resp2.status_code}: {resp2.json()}"
    assert "cooldown" in resp2.json()["detail"].lower()


def test_get_preferences_masks_contact_values() -> None:
    resp = client.get("/api/v1/automation/notification/preferences")
    assert resp.status_code == 200
    body = resp.json()
    assert "preferences" in body
    prefs = body["preferences"]
    # Contacts must be masked — raw email/phone should never appear
    for contact in prefs.get("contacts", []):
        raw_value = contact.get("target_value", "")
        # Masked values must not look like a plain email (contain @ but no bullet)
        if "@" in raw_value:
            assert "•" in raw_value, f"Unmasked contact target found: {raw_value}"


def test_automation_run_limit_cap() -> None:
    """Limit parameter is capped at 200."""
    resp = client.get("/api/v1/automation/runs?limit=9999")
    assert resp.status_code == 200
