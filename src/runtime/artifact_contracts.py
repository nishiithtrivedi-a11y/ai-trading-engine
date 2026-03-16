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


def get_artifact_contract(run_mode: RunMode | str) -> ArtifactContract:
    if isinstance(run_mode, RunMode):
        key = run_mode
    else:
        key = RunMode(str(run_mode).strip().lower())

    contract = _CONTRACTS.get(key)
    if contract is None:
        raise ArtifactContractError(f"No artifact contract configured for run mode '{key.value}'")
    return contract


def list_artifact_contracts() -> dict[str, ArtifactContract]:
    return {mode.value: contract for mode, contract in _CONTRACTS.items()}
