"""
Daily dry-run orchestration for scanner -> monitoring -> decision workflows.

This module is intentionally non-live and only produces research artifacts.
It does not place broker orders.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from src.decision.config import DecisionConfig, DecisionExportConfig
from src.decision.exporter import DecisionExporter
from src.decision.pick_engine import PickEngine
from src.monitoring.config import (
    MonitoringConfig,
    MonitoringExportConfig,
    RegimeDetectorConfig,
    RelativeStrengthConfig,
    SnapshotConfig,
    WatchlistDefinition,
)
from src.monitoring.market_monitor import MarketMonitor
from src.runtime.artifact_contracts import get_artifact_contract_by_id
from src.runtime.contract_validation import validate_artifact_contract
from src.runtime.output_manifest import write_output_manifest
from src.runtime.run_profiles import RunMode
from src.scanners.config import ExportConfig, ScannerConfig, StrategyScanSpec, normalize_timeframe
from src.scanners.engine import StockScannerEngine
from src.scanners.exporter import ScanExporter
from src.strategies.rsi_reversion import RSIReversionStrategy
from src.strategies.sma_crossover import SMACrossoverStrategy


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DailyDryRunError(RuntimeError):
    """Raised when daily dry-run orchestration fails."""


@dataclass
class DailyDryRunConfig:
    output_dir: str = "output/daily_dry_run"
    provider_name: str = "csv"
    data_dir: str = "data"
    symbols: list[str] = field(
        default_factory=lambda: [
            "RELIANCE.NS",
            "TCS.NS",
            "INFY.NS",
            "HDFCBANK.NS",
            "ICICIBANK.NS",
        ]
    )
    symbols_limit: int = 3
    timeframe: str = "1D"
    include_paper_handoff: bool = True

    def __post_init__(self) -> None:
        if self.symbols_limit < 1:
            raise ValueError("symbols_limit must be >= 1")
        self.timeframe = normalize_timeframe(self.timeframe)
        self.symbols = [str(symbol).strip().upper() for symbol in self.symbols if str(symbol).strip()]
        if not self.symbols:
            raise ValueError("symbols cannot be empty")


@dataclass
class DailyDryRunStageResult:
    stage_name: str
    success: bool
    output_dir: str
    contract_id: str
    manifest_path: Optional[str] = None
    artifacts: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    validation: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        public_metrics = {
            key: value
            for key, value in self.metrics.items()
            if not str(key).startswith("_")
        }
        return {
            "stage_name": self.stage_name,
            "success": self.success,
            "output_dir": self.output_dir,
            "contract_id": self.contract_id,
            "manifest_path": self.manifest_path,
            "artifacts": dict(self.artifacts),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "validation": dict(self.validation),
            "metrics": public_metrics,
        }


@dataclass
class DailyDryRunResult:
    success: bool
    generated_at: str
    output_dir: str
    provider_name: str
    symbols: list[str]
    timeframe: str
    stages: list[DailyDryRunStageResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    exports: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "generated_at": self.generated_at,
            "output_dir": self.output_dir,
            "provider_name": self.provider_name,
            "symbols": list(self.symbols),
            "timeframe": self.timeframe,
            "stages": [stage.to_dict() for stage in self.stages],
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "exports": dict(self.exports),
        }


@dataclass
class DailyDryRunOrchestrator:
    config: DailyDryRunConfig

    def run(self) -> DailyDryRunResult:
        output_root = Path(self.config.output_dir)
        output_root.mkdir(parents=True, exist_ok=True)
        symbols = self.config.symbols[: self.config.symbols_limit]

        result = DailyDryRunResult(
            success=True,
            generated_at=_utc_now_iso(),
            output_dir=str(output_root),
            provider_name=self.config.provider_name,
            symbols=symbols,
            timeframe=self.config.timeframe,
        )

        scan_result = None
        monitoring_result = None
        decision_result = None

        scanner_stage = self._run_scanner_stage(symbols)
        result.stages.append(scanner_stage)
        if not scanner_stage.success:
            result.success = False
            result.errors.extend(scanner_stage.errors)
            return self._finalize(result)

        scan_result = scanner_stage.metrics.get("_scan_result")
        if scan_result is None:
            result.success = False
            result.errors.append("Scanner stage did not produce scan result object")
            return self._finalize(result)

        monitoring_stage = self._run_monitoring_stage(symbols)
        result.stages.append(monitoring_stage)
        if not monitoring_stage.success:
            result.success = False
            result.errors.extend(monitoring_stage.errors)
            return self._finalize(result)

        monitoring_result = monitoring_stage.metrics.get("_monitoring_result")
        if monitoring_result is None:
            result.success = False
            result.errors.append("Monitoring stage did not produce monitoring result object")
            return self._finalize(result)

        decision_stage = self._run_decision_stage(monitoring_result)
        result.stages.append(decision_stage)
        if not decision_stage.success:
            result.success = False
            result.errors.extend(decision_stage.errors)
            return self._finalize(result)

        decision_result = decision_stage.metrics.get("_decision_result")
        if decision_result is None:
            result.success = False
            result.errors.append("Decision stage did not produce decision result object")
            return self._finalize(result)

        return self._finalize(result)

    def _run_scanner_stage(self, symbols: list[str]) -> DailyDryRunStageResult:
        stage_dir = Path(self.config.output_dir) / "scanner"
        stage_dir.mkdir(parents=True, exist_ok=True)
        contract = get_artifact_contract_by_id("scanner_bundle_v1")
        errors: list[str] = []

        try:
            universe_path = stage_dir / "scanner_universe.csv"
            pd.DataFrame({"symbol": symbols}).to_csv(universe_path, index=False)

            scanner_cfg = ScannerConfig(
                universe_name="custom",
                custom_universe_file=str(universe_path),
                provider_name=self.config.provider_name,
                data_dir=self.config.data_dir,
                timeframes=[self.config.timeframe],
                strategy_specs=[
                    StrategyScanSpec(
                        strategy_class=RSIReversionStrategy,
                        params={"rsi_period": 14, "oversold": 30, "overbought": 70},
                        timeframes=[self.config.timeframe],
                    ),
                    StrategyScanSpec(
                        strategy_class=SMACrossoverStrategy,
                        params={"fast_period": 20, "slow_period": 50},
                        timeframes=[self.config.timeframe],
                    ),
                ],
                export=ExportConfig(
                    output_dir=str(stage_dir),
                    csv_filename="opportunities.csv",
                    json_filename="opportunities.json",
                    write_csv=True,
                    write_json=True,
                ),
            )
            engine = StockScannerEngine(scanner_config=scanner_cfg)
            scan_result = engine.run(export=False)
            exporter = ScanExporter()
            outputs = exporter.export_all(scan_result, scanner_cfg.export, top_n=scanner_cfg.top_n)

            manifest_artifacts = {
                "opportunities_csv": outputs["csv"],
                "opportunities_json": outputs["json"],
                "run_manifest": stage_dir / "run_manifest.json",
            }
            manifest_path = write_output_manifest(
                output_dir=stage_dir,
                run_mode=RunMode.RESEARCH,
                provider_name=self.config.provider_name,
                artifacts=manifest_artifacts,
                metadata={
                    "stage": "scanner",
                    "symbols_evaluated": len(symbols),
                    "opportunities": len(scan_result.opportunities),
                },
                contract_id=contract.contract_id,
                expected_artifacts=contract.required_names,
                schema_version=contract.schema_version,
                safety_mode=contract.safety_mode,
            )
            validation = validate_artifact_contract(
                contract_id=contract.contract_id,
                output_dir=stage_dir,
                manifest_path=manifest_path,
            )
            if not validation.is_valid:
                errors.append(f"Scanner contract validation failed: {validation.to_dict()}")

            return DailyDryRunStageResult(
                stage_name="scanner",
                success=(len(errors) == 0),
                output_dir=str(stage_dir),
                contract_id=contract.contract_id,
                manifest_path=str(manifest_path),
                artifacts={
                    "opportunities_csv": str(outputs["csv"]),
                    "opportunities_json": str(outputs["json"]),
                    "run_manifest": str(manifest_path),
                },
                errors=errors,
                validation=validation.to_dict(),
                metrics={
                    "symbols_scanned": scan_result.num_symbols_scanned,
                    "opportunities": len(scan_result.opportunities),
                    "_scan_result": scan_result,
                },
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))
            return DailyDryRunStageResult(
                stage_name="scanner",
                success=False,
                output_dir=str(stage_dir),
                contract_id=contract.contract_id,
                errors=errors,
            )

    def _run_monitoring_stage(self, symbols: list[str]) -> DailyDryRunStageResult:
        stage_dir = Path(self.config.output_dir) / "monitoring"
        stage_dir.mkdir(parents=True, exist_ok=True)
        contract = get_artifact_contract_by_id("monitoring_bundle_v1")
        errors: list[str] = []

        try:
            benchmark = symbols[0]
            scanner_cfg = ScannerConfig(
                provider_name=self.config.provider_name,
                data_dir=self.config.data_dir,
                universe_name="custom",
                timeframes=[self.config.timeframe],
                strategy_specs=[
                    StrategyScanSpec(
                        strategy_class=RSIReversionStrategy,
                        params={"rsi_period": 14, "oversold": 30, "overbought": 70},
                        timeframes=[self.config.timeframe],
                    ),
                    StrategyScanSpec(
                        strategy_class=SMACrossoverStrategy,
                        params={"fast_period": 20, "slow_period": 50},
                        timeframes=[self.config.timeframe],
                    ),
                ],
            )
            monitoring_cfg = MonitoringConfig(
                scanner_config=scanner_cfg,
                watchlists=[
                    WatchlistDefinition(
                        name="daily_dry_run",
                        symbols=symbols,
                    )
                ],
                regime=RegimeDetectorConfig(
                    benchmark_symbol=benchmark,
                    timeframe=self.config.timeframe,
                    use_benchmark=True,
                    fallback_to_symbol=True,
                ),
                relative_strength=RelativeStrengthConfig(
                    benchmark_symbol=benchmark,
                    timeframe=self.config.timeframe,
                    allow_missing_benchmark=True,
                ),
                snapshot=SnapshotConfig(top_n=10, min_score=0.0),
                export=MonitoringExportConfig(
                    output_dir=str(stage_dir),
                    write_csv=True,
                    write_json=True,
                ),
            )
            monitor = MarketMonitor(config=monitoring_cfg)
            monitoring_result = monitor.run(export=True, watchlist_names=["daily_dry_run"])
            output_map = {k: Path(v) for k, v in monitoring_result.exports.items()}

            manifest_artifacts = {
                "alerts_csv": output_map["alerts_csv"],
                "top_picks_csv": output_map["top_picks_csv"],
                "relative_strength_csv": output_map["relative_strength_csv"],
                "alerts_json": output_map["alerts_json"],
                "market_snapshot_json": output_map["market_snapshot_json"],
                "relative_strength_json": output_map["relative_strength_json"],
                "regime_summary_json": output_map["regime_summary_json"],
                "monitoring_run_manifest": output_map["manifest_json"],
                "run_manifest": stage_dir / "run_manifest.json",
            }
            manifest_path = write_output_manifest(
                output_dir=stage_dir,
                run_mode=RunMode.RESEARCH,
                provider_name=self.config.provider_name,
                artifacts=manifest_artifacts,
                metadata={
                    "stage": "monitoring",
                    "symbols_evaluated": (
                        monitoring_result.scan_result.num_symbols_scanned
                        if monitoring_result.scan_result is not None
                        else 0
                    ),
                    "alerts": len(monitoring_result.alerts),
                },
                contract_id=contract.contract_id,
                expected_artifacts=contract.required_names,
                schema_version=contract.schema_version,
                safety_mode=contract.safety_mode,
            )
            validation = validate_artifact_contract(
                contract_id=contract.contract_id,
                output_dir=stage_dir,
                manifest_path=manifest_path,
            )
            if not validation.is_valid:
                errors.append(f"Monitoring contract validation failed: {validation.to_dict()}")

            return DailyDryRunStageResult(
                stage_name="monitoring",
                success=(len(errors) == 0),
                output_dir=str(stage_dir),
                contract_id=contract.contract_id,
                manifest_path=str(manifest_path),
                artifacts={k: str(v) for k, v in manifest_artifacts.items()},
                warnings=list(monitoring_result.warnings),
                errors=errors + list(monitoring_result.errors),
                validation=validation.to_dict(),
                metrics={
                    "alerts": len(monitoring_result.alerts),
                    "relative_strength_rows": len(monitoring_result.relative_strength),
                    "selected_scan_opportunities": (
                        len(monitoring_result.scan_result.opportunities)
                        if monitoring_result.scan_result is not None
                        else 0
                    ),
                    "_monitoring_result": monitoring_result,
                },
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))
            return DailyDryRunStageResult(
                stage_name="monitoring",
                success=False,
                output_dir=str(stage_dir),
                contract_id=contract.contract_id,
                errors=errors,
            )

    def _run_decision_stage(self, monitoring_result) -> DailyDryRunStageResult:  # noqa: ANN001
        stage_dir = Path(self.config.output_dir) / "decision"
        stage_dir.mkdir(parents=True, exist_ok=True)
        contract = get_artifact_contract_by_id("decision_bundle_v1")
        errors: list[str] = []

        try:
            decision_cfg = DecisionConfig(
                export=DecisionExportConfig(
                    output_dir=str(stage_dir),
                    write_csv=True,
                    write_json=True,
                )
            )
            pick_engine = PickEngine(decision_config=decision_cfg)
            decision_result = pick_engine.run(monitoring_result=monitoring_result)
            exporter = DecisionExporter()
            exports = exporter.export_all(decision_result, decision_cfg.export)
            decision_result.exports = {k: str(v) for k, v in exports.items()}

            manifest_artifacts: dict[str, Path] = {
                "intraday_csv": exports["intraday_csv"],
                "swing_csv": exports["swing_csv"],
                "positional_csv": exports["positional_csv"],
                "rejected_csv": exports["rejected_csv"],
                "summary_json": exports["summary_json"],
                "decision_manifest": exports["manifest_json"],
                "run_manifest": stage_dir / "run_manifest.json",
            }
            if self.config.include_paper_handoff:
                handoff_path = self._write_paper_handoff(decision_result, stage_dir)
                manifest_artifacts["paper_handoff_candidates"] = handoff_path

            manifest_path = write_output_manifest(
                output_dir=stage_dir,
                run_mode=RunMode.RESEARCH,
                provider_name=self.config.provider_name,
                artifacts=manifest_artifacts,
                metadata={
                    "stage": "decision",
                    "selected_total": len(decision_result.selected_picks),
                    "rejected_total": len(decision_result.rejected_opportunities),
                },
                contract_id=contract.contract_id,
                expected_artifacts=contract.required_names,
                schema_version=contract.schema_version,
                safety_mode=contract.safety_mode,
            )
            validation = validate_artifact_contract(
                contract_id=contract.contract_id,
                output_dir=stage_dir,
                manifest_path=manifest_path,
            )
            if not validation.is_valid:
                errors.append(f"Decision contract validation failed: {validation.to_dict()}")

            return DailyDryRunStageResult(
                stage_name="decision",
                success=(len(errors) == 0),
                output_dir=str(stage_dir),
                contract_id=contract.contract_id,
                manifest_path=str(manifest_path),
                artifacts={k: str(v) for k, v in manifest_artifacts.items()},
                warnings=list(decision_result.warnings),
                errors=errors + list(decision_result.errors),
                validation=validation.to_dict(),
                metrics={
                    "selected_total": len(decision_result.selected_picks),
                    "intraday_total": len(decision_result.top_intraday),
                    "swing_total": len(decision_result.top_swing),
                    "positional_total": len(decision_result.top_positional),
                    "_decision_result": decision_result,
                },
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))
            return DailyDryRunStageResult(
                stage_name="decision",
                success=False,
                output_dir=str(stage_dir),
                contract_id=contract.contract_id,
                errors=errors,
            )

    @staticmethod
    def _write_paper_handoff(decision_result, decision_dir: Path) -> Path:  # noqa: ANN001
        handoff_path = decision_dir / "paper_handoff_candidates.csv"
        rows = []
        for pick in decision_result.selected_picks:
            plan = pick.trade_plan
            rows.append(
                {
                    "symbol": plan.symbol,
                    "timeframe": plan.timeframe,
                    "strategy_name": plan.strategy_name,
                    "entry_price": plan.entry_price,
                    "stop_loss": plan.stop_loss,
                    "target_price": plan.target_price,
                    "risk_reward": plan.risk_reward,
                    "horizon": plan.horizon.value,
                    "conviction_score": pick.conviction_score,
                }
            )
        pd.DataFrame(rows).to_csv(handoff_path, index=False)
        return handoff_path

    def _finalize(self, result: DailyDryRunResult) -> DailyDryRunResult:
        output_root = Path(result.output_dir)
        payload = result.to_dict()
        payload["safety_note"] = "No live broker orders were placed."
        payload["contract_validation_passed"] = all(
            stage.validation.get("is_valid", False) if stage.validation else False
            for stage in result.stages
        )

        summary_json = output_root / "daily_dry_run_summary.json"
        summary_md = output_root / "daily_dry_run_summary.md"

        summary_json.write_text(
            json.dumps(payload, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
        summary_md.write_text(self._to_markdown(result), encoding="utf-8")

        for stage in result.stages:
            if stage.manifest_path:
                result.exports[f"{stage.stage_name}_run_manifest"] = stage.manifest_path
            if stage.stage_name == "decision" and "paper_handoff_candidates" in stage.artifacts:
                result.exports["paper_handoff_candidates"] = stage.artifacts["paper_handoff_candidates"]

        result.exports["daily_dry_run_summary_json"] = str(summary_json)
        result.exports["daily_dry_run_summary_md"] = str(summary_md)
        return result

    @staticmethod
    def _to_markdown(result: DailyDryRunResult) -> str:
        lines = [
            "# Daily Dry-Run Summary",
            "",
            f"- Generated at: {result.generated_at}",
            f"- Success: {result.success}",
            f"- Provider: {result.provider_name}",
            f"- Timeframe: {result.timeframe}",
            f"- Symbols: {', '.join(result.symbols)}",
            "",
            "## Stage Results",
        ]
        for stage in result.stages:
            lines.extend(
                [
                    f"### {stage.stage_name}",
                    f"- Success: {stage.success}",
                    f"- Contract: {stage.contract_id}",
                    f"- Output dir: {stage.output_dir}",
                    f"- Manifest: {stage.manifest_path or 'N/A'}",
                ]
            )
            if stage.metrics:
                lines.append("- Metrics:")
                for key, value in stage.metrics.items():
                    if str(key).startswith("_"):
                        continue
                    lines.append(f"  - {key}: {value}")
            if stage.errors:
                lines.append("- Errors:")
                for err in stage.errors:
                    lines.append(f"  - {err}")
            if stage.warnings:
                lines.append("- Warnings:")
                for warn in stage.warnings:
                    lines.append(f"  - {warn}")
            lines.append("")

        lines.extend(
            [
                "## Safety",
                "- This dry-run is research-only.",
                "- No live broker orders were placed.",
                "",
            ]
        )
        return "\n".join(lines)
