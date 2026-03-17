"""
Artifact contract definitions for runtime workflows.

Contracts define the expected output bundle per run mode so downstream
automation can validate artifacts deterministically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from src.runtime.run_profiles import RunMode


class ArtifactContractError(ValueError):
    """Raised when artifact contract lookup or validation setup fails."""


class ArtifactType(str, Enum):
    CSV = "csv"
    JSON = "json"
    MARKDOWN = "markdown"
    MANIFEST = "manifest"


@dataclass(frozen=True)
class ArtifactSpec:
    name: str
    filename: str
    artifact_type: ArtifactType
    description: str = ""


@dataclass(frozen=True)
class ArtifactContract:
    contract_id: str
    run_mode: RunMode
    producer: str
    schema_version: str = "1.0"
    required: tuple[ArtifactSpec, ...] = field(default_factory=tuple)
    optional: tuple[ArtifactSpec, ...] = field(default_factory=tuple)
    required_manifest_fields: tuple[str, ...] = (
        "schema_version",
        "run_mode",
        "provider_name",
        "generated_at",
        "artifacts",
    )
    safety_mode: str = "no_live_execution"

    @property
    def required_names(self) -> tuple[str, ...]:
        return tuple(spec.name for spec in self.required)

    @property
    def optional_names(self) -> tuple[str, ...]:
        return tuple(spec.name for spec in self.optional)

    @property
    def all_names(self) -> tuple[str, ...]:
        return self.required_names + self.optional_names


_CONTRACTS: dict[RunMode, ArtifactContract] = {
    RunMode.RESEARCH: ArtifactContract(
        contract_id="research_runner_v1",
        run_mode=RunMode.RESEARCH,
        producer="scripts/run_nifty50_zerodha_research.py",
        required=(
            ArtifactSpec("all_results", "all_results.csv", ArtifactType.CSV),
            ArtifactSpec("top_ranked", "top_ranked.csv", ArtifactType.CSV),
            ArtifactSpec("summary", "summary.md", ArtifactType.MARKDOWN),
            ArtifactSpec("run_manifest", "run_manifest.json", ArtifactType.MANIFEST),
        ),
    ),
    RunMode.PAPER: ArtifactContract(
        contract_id="paper_runner_v1",
        run_mode=RunMode.PAPER,
        producer="scripts/run_paper_trading.py",
        required=(
            ArtifactSpec("paper_orders", "paper_orders.csv", ArtifactType.CSV),
            ArtifactSpec("paper_positions", "paper_positions.csv", ArtifactType.CSV),
            ArtifactSpec("paper_pnl", "paper_pnl.csv", ArtifactType.CSV),
            ArtifactSpec("paper_journal", "paper_journal.csv", ArtifactType.CSV),
            ArtifactSpec("paper_state", "paper_state.json", ArtifactType.JSON),
            ArtifactSpec(
                "paper_session_summary",
                "paper_session_summary.md",
                ArtifactType.MARKDOWN,
            ),
            ArtifactSpec("run_manifest", "run_manifest.json", ArtifactType.MANIFEST),
        ),
    ),
    RunMode.LIVE_SAFE: ArtifactContract(
        contract_id="live_safe_runner_v1",
        run_mode=RunMode.LIVE_SAFE,
        producer="scripts/run_live_signal_pipeline.py",
        required=(
            ArtifactSpec("signals", "signals.csv", ArtifactType.CSV),
            ArtifactSpec("watchlist", "watchlist.csv", ArtifactType.CSV),
            ArtifactSpec("regime_snapshot", "regime_snapshot.csv", ArtifactType.CSV),
            ArtifactSpec("session_state", "session_state.json", ArtifactType.JSON),
            ArtifactSpec("session_summary", "session_summary.md", ArtifactType.MARKDOWN),
            ArtifactSpec("run_manifest", "run_manifest.json", ArtifactType.MANIFEST),
        ),
        optional=(
            ArtifactSpec(
                "paper_handoff",
                "paper_handoff_signals.csv",
                ArtifactType.CSV,
            ),
        ),
    ),
}

_MID_PIPELINE_CONTRACTS: dict[str, ArtifactContract] = {
    "scanner_bundle_v1": ArtifactContract(
        contract_id="scanner_bundle_v1",
        run_mode=RunMode.RESEARCH,
        producer="src/scanners/exporter.py",
        required=(
            ArtifactSpec("opportunities_csv", "opportunities.csv", ArtifactType.CSV),
            ArtifactSpec("opportunities_json", "opportunities.json", ArtifactType.JSON),
            ArtifactSpec("run_manifest", "run_manifest.json", ArtifactType.MANIFEST),
        ),
    ),
    "monitoring_bundle_v1": ArtifactContract(
        contract_id="monitoring_bundle_v1",
        run_mode=RunMode.RESEARCH,
        producer="src/monitoring/exporter.py",
        required=(
            ArtifactSpec("alerts_csv", "alerts.csv", ArtifactType.CSV),
            ArtifactSpec("top_picks_csv", "top_picks.csv", ArtifactType.CSV),
            ArtifactSpec("relative_strength_csv", "relative_strength.csv", ArtifactType.CSV),
            ArtifactSpec("alerts_json", "alerts.json", ArtifactType.JSON),
            ArtifactSpec("market_snapshot_json", "market_snapshot.json", ArtifactType.JSON),
            ArtifactSpec("relative_strength_json", "relative_strength.json", ArtifactType.JSON),
            ArtifactSpec("regime_summary_json", "regime_summary.json", ArtifactType.JSON),
            ArtifactSpec(
                "monitoring_run_manifest",
                "monitoring_run_manifest.json",
                ArtifactType.JSON,
            ),
            ArtifactSpec("run_manifest", "run_manifest.json", ArtifactType.MANIFEST),
        ),
    ),
    "decision_bundle_v1": ArtifactContract(
        contract_id="decision_bundle_v1",
        run_mode=RunMode.RESEARCH,
        producer="src/decision/exporter.py",
        required=(
            ArtifactSpec("intraday_csv", "decision_top_intraday.csv", ArtifactType.CSV),
            ArtifactSpec("swing_csv", "decision_top_swing.csv", ArtifactType.CSV),
            ArtifactSpec("positional_csv", "decision_top_positional.csv", ArtifactType.CSV),
            ArtifactSpec("rejected_csv", "decision_rejected.csv", ArtifactType.CSV),
            ArtifactSpec("summary_json", "decision_summary.json", ArtifactType.JSON),
            ArtifactSpec("decision_manifest", "decision_manifest.json", ArtifactType.JSON),
            ArtifactSpec("run_manifest", "run_manifest.json", ArtifactType.MANIFEST),
        ),
        optional=(
            ArtifactSpec(
                "paper_handoff_candidates",
                "paper_handoff_candidates.csv",
                ArtifactType.CSV,
            ),
        ),
    ),
}

_CONTRACTS_BY_ID: dict[str, ArtifactContract] = {
    contract.contract_id: contract
    for contract in (
        *tuple(_CONTRACTS.values()),
        *tuple(_MID_PIPELINE_CONTRACTS.values()),
    )
}


def get_artifact_contract(run_mode: RunMode | str) -> ArtifactContract:
    if isinstance(run_mode, RunMode):
        key = run_mode
    else:
        key = RunMode(str(run_mode).strip().lower())

    contract = _CONTRACTS.get(key)
    if contract is None:
        raise ArtifactContractError(f"No artifact contract configured for run mode '{key.value}'")
    return contract


def get_artifact_contract_by_id(contract_id: str) -> ArtifactContract:
    clean_id = str(contract_id).strip()
    if not clean_id:
        raise ArtifactContractError("contract_id cannot be empty")
    contract = _CONTRACTS_BY_ID.get(clean_id)
    if contract is None:
        raise ArtifactContractError(f"No artifact contract configured for id '{clean_id}'")
    return contract


def list_artifact_contracts() -> dict[str, ArtifactContract]:
    return {mode.value: contract for mode, contract in _CONTRACTS.items()}


def list_artifact_contracts_by_id() -> dict[str, ArtifactContract]:
    return dict(_CONTRACTS_BY_ID)
