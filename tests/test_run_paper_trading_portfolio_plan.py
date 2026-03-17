from __future__ import annotations

import json
from pathlib import Path

from scripts.run_paper_trading import load_portfolio_plan_overrides


def test_load_portfolio_plan_overrides_parses_selected_items(tmp_path: Path) -> None:
    payload = {
        "portfolio_plan": {
            "summary": {"drawdown_mode": "reduced_risk"},
            "items": [
                {"symbol": "RELIANCE.NS", "selection_status": "selected", "recommended_quantity": 12},
                {"symbol": "TCS.NS", "selection_status": "resized", "recommended_quantity": 8},
                {"symbol": "INFY.NS", "selection_status": "rejected", "recommended_quantity": 0},
            ],
        }
    }
    path = tmp_path / "portfolio_plan.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    overrides, allow_new_risk, drawdown_mode = load_portfolio_plan_overrides(str(path))

    assert allow_new_risk is True
    assert drawdown_mode == "reduced_risk"
    assert set(overrides.keys()) == {"RELIANCE.NS", "TCS.NS"}


def test_load_portfolio_plan_overrides_detects_no_new_risk(tmp_path: Path) -> None:
    payload = {
        "summary": {"drawdown_mode": "no_new_risk"},
        "items": [{"symbol": "RELIANCE.NS", "selection_status": "selected", "recommended_quantity": 5}],
    }
    path = tmp_path / "portfolio_plan_root.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    overrides, allow_new_risk, drawdown_mode = load_portfolio_plan_overrides(str(path))
    assert overrides
    assert drawdown_mode == "no_new_risk"
    assert allow_new_risk is False

