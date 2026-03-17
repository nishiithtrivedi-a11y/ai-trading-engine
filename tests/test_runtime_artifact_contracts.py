from __future__ import annotations

from src.runtime.artifact_contracts import (
    get_artifact_contract,
    get_artifact_contract_by_id,
    list_artifact_contracts,
    list_artifact_contracts_by_id,
)
from src.runtime.run_profiles import RunMode


def test_artifact_contracts_exist_for_all_run_modes() -> None:
    contracts = list_artifact_contracts()
    assert set(contracts.keys()) == {"research", "paper", "live_safe"}


def test_live_safe_contract_contains_optional_paper_handoff() -> None:
    contract = get_artifact_contract(RunMode.LIVE_SAFE)
    assert "paper_handoff" in contract.optional_names
    assert "run_manifest" in contract.required_names


def test_paper_contract_required_outputs_are_explicit() -> None:
    contract = get_artifact_contract("paper")
    expected = {
        "paper_orders",
        "paper_positions",
        "paper_pnl",
        "paper_journal",
        "paper_state",
        "paper_session_summary",
        "run_manifest",
    }
    assert set(contract.required_names) == expected


def test_mid_pipeline_contracts_are_registered_by_id() -> None:
    contracts = list_artifact_contracts_by_id()
    assert "scanner_bundle_v1" in contracts
    assert "monitoring_bundle_v1" in contracts
    assert "decision_bundle_v1" in contracts
    assert "scanner_runner_v1" in contracts
    assert "monitoring_runner_v1" in contracts
    assert "decision_runner_v1" in contracts

    scanner_contract = get_artifact_contract_by_id("scanner_bundle_v1")
    assert scanner_contract.run_mode == RunMode.RESEARCH
    assert "run_manifest" in scanner_contract.required_names

    decision_runner_contract = get_artifact_contract_by_id("decision_runner_v1")
    assert "decision_selected_json" in decision_runner_contract.required_names
    assert "portfolio_plan_json" in decision_runner_contract.required_names
