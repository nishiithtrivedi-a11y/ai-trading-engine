#!/usr/bin/env python3
"""
Standalone decision operational runner.

Supports:
- standalone decision runs
- monitoring -> decision chaining via explicit monitoring artifact directory
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from src.data.nse_universe import NSEUniverseLoader  # noqa: E402
from src.decision import DecisionConfig, DecisionExporter, PickEngine  # noqa: E402
from src.monitoring import (  # noqa: E402
    MarketMonitor,
    MonitoringConfig,
    MonitoringRunResult,
    RegimeAssessment,
    RegimeDetectorConfig,
    RegimeState,
    RelativeStrengthConfig,
    RelativeStrengthSnapshot,
    SnapshotConfig,
    WatchlistDefinition,
)
from src.runtime import (  # noqa: E402
    RunMode,
    RunnerArtifactResolutionError,
    assert_artifact_contract,
    enforce_runtime_safety,
    get_artifact_contract_by_id,
    get_runner_schedule_profile,
    load_json_file,
    resolve_latest_runner_dir,
    resolve_runner_output_dir,
    validate_provider_for_mode,
    validate_symbol_inputs,
    write_output_manifest,
    write_runner_artifacts_meta,
)
from src.scanners import (  # noqa: E402
    Opportunity,
    OpportunityClass,
    OpportunitySide,
    ScanResult,
    ScannerConfig,
    StrategyScanSpec,
    normalize_timeframe,
)
from src.strategies.rsi_reversion import RSIReversionStrategy  # noqa: E402
from src.strategies.sma_crossover import SMACrossoverStrategy  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run standalone decision workflow.")
    parser.add_argument("--provider", default="indian_csv", help="Provider name.")
    parser.add_argument("--symbols", nargs="*", default=None, help="Explicit symbol list.")
    parser.add_argument("--symbols-file", default="", help="CSV with symbol/ticker column.")
    parser.add_argument("--universe", default="nifty50", help="Universe name.")
    parser.add_argument(
        "--interval",
        default="",
        choices=["", "day", "5minute", "15minute", "60minute", "1D", "5m", "15m", "1h"],
        help="Decision interval override.",
    )
    parser.add_argument(
        "--profile",
        default="eod",
        choices=["morning", "intraday", "eod"],
        help="Operational schedule profile.",
    )
    parser.add_argument("--output-dir", default="output/decision", help="Output root directory.")
    parser.add_argument(
        "--monitoring-input-dir",
        "--input-dir",
        dest="monitoring_input_dir",
        default="",
        help="Optional monitoring artifact directory for chained decision run.",
    )
    parser.add_argument(
        "--use-latest-monitoring-input",
        action="store_true",
        help="Resolve latest monitoring run under output/monitoring when monitoring input is omitted.",
    )
    parser.add_argument("--run-once", action="store_true", help="No-op; accepted for CLI consistency.")
    parser.add_argument("--max-symbols", type=int, default=0, help="Optional max symbols.")
    parser.add_argument("--data-dir", default="data", help="CSV data directory.")
    parser.add_argument("--paper-handoff", action="store_true", help="Write paper_handoff_candidates.csv.")
    parser.add_argument("--log-level", default="INFO", help="Reserved for future logging control.")
    parser.add_argument(
        "--no-timestamped-output",
        action="store_true",
        help="Write artifacts directly into --output-dir.",
    )
    args = parser.parse_args()

    validate_symbol_inputs(
        symbols=args.symbols,
        universe=args.universe,
        universe_file=args.symbols_file or None,
    )
    if args.max_symbols < 0:
        parser.error("--max-symbols must be >= 0")
    return args


def _interval_to_timeframe(interval: str, profile_interval: str) -> str:
    if not interval:
        interval = profile_interval
    mapping = {
        "day": "1D",
        "1d": "1D",
        "1D": "1D",
        "5minute": "5m",
        "5m": "5m",
        "15minute": "15m",
        "15m": "15m",
        "60minute": "1h",
        "1h": "1h",
    }
    return normalize_timeframe(mapping.get(str(interval).strip(), str(interval).strip()))


def _resolve_monitoring_input_dir(args: argparse.Namespace) -> Path | None:
    if args.monitoring_input_dir:
        return Path(args.monitoring_input_dir)
    if args.use_latest_monitoring_input:
        return resolve_latest_runner_dir(output_dir="output/monitoring")
    return None


def _opportunity_from_dict(row: dict[str, Any]) -> Opportunity:
    classification = OpportunityClass(str(row.get("classification", "intraday")).strip().lower())
    side = OpportunitySide(str(row.get("side", "long")).strip().lower())
    return Opportunity(
        symbol=str(row.get("symbol", "")).strip().upper(),
        timeframe=str(row.get("timeframe", "1D")),
        strategy_name=str(row.get("strategy_name", "")),
        signal=str(row.get("signal", "hold")),
        timestamp=pd.Timestamp(row.get("timestamp")),
        classification=classification,
        entry_price=float(row.get("entry_price", 0.0)),
        stop_loss=float(row.get("stop_loss", 0.0)),
        target_price=float(row.get("target_price", 0.0)),
        side=side,
        score=float(row.get("score", 0.0)),
        reasons=[str(value) for value in row.get("reasons", [])]
        if isinstance(row.get("reasons"), list)
        else [],
        metadata=dict(row.get("metadata", {})) if isinstance(row.get("metadata"), dict) else {},
        score_signal=(float(row["score_signal"]) if row.get("score_signal") is not None else None),
        score_rr=(float(row["score_rr"]) if row.get("score_rr") is not None else None),
        score_trend=(float(row["score_trend"]) if row.get("score_trend") is not None else None),
        score_liquidity=(float(row["score_liquidity"]) if row.get("score_liquidity") is not None else None),
        score_freshness=(float(row["score_freshness"]) if row.get("score_freshness") is not None else None),
        rank=(int(row["rank"]) if row.get("rank") is not None else None),
    )


def _monitoring_result_from_artifacts(monitoring_dir: Path) -> MonitoringRunResult:
    input_path = monitoring_dir / "monitoring_decision_input.json"
    if not input_path.exists():
        raise FileNotFoundError(
            f"monitoring_decision_input.json not found in {monitoring_dir}"
        )

    payload = load_json_file(input_path)
    scan_payload = payload.get("scan_result", {}) if isinstance(payload, dict) else {}
    opportunities = [
        _opportunity_from_dict(row)
        for row in scan_payload.get("opportunities", [])
        if isinstance(row, dict)
    ]
    scan_result = ScanResult(
        opportunities=opportunities,
        universe_name=str(scan_payload.get("universe_name", "")),
        provider_name=str(scan_payload.get("provider_name", "")),
        num_symbols_scanned=int(scan_payload.get("num_symbols_scanned", 0)),
        num_jobs=int(scan_payload.get("num_jobs", 0)),
        num_errors=int(scan_payload.get("num_errors", 0)),
        errors=list(scan_payload.get("errors", [])),
    )

    regime_payload = payload.get("regime_assessment")
    regime_assessment: Optional[RegimeAssessment] = None
    if isinstance(regime_payload, dict) and regime_payload.get("regime"):
        regime_assessment = RegimeAssessment(
            regime=RegimeState(str(regime_payload.get("regime")).strip().lower()),
            timestamp=pd.Timestamp(regime_payload.get("timestamp")),
            trend_score=(
                float(regime_payload["trend_score"])
                if regime_payload.get("trend_score") is not None
                else None
            ),
            volatility_score=(
                float(regime_payload["volatility_score"])
                if regime_payload.get("volatility_score") is not None
                else None
            ),
            range_score=(
                float(regime_payload["range_score"])
                if regime_payload.get("range_score") is not None
                else None
            ),
            reason=str(regime_payload.get("reason", "")),
            metadata=dict(regime_payload.get("metadata", {})),
        )

    rs_rows: list[RelativeStrengthSnapshot] = []
    for row in payload.get("relative_strength", []) if isinstance(payload, dict) else []:
        if not isinstance(row, dict):
            continue
        rs_rows.append(
            RelativeStrengthSnapshot(
                symbol=str(row.get("symbol", "")).strip().upper(),
                score=float(row.get("score", 0.0)),
                lookback_returns=dict(row.get("lookback_returns", {})),
                benchmark_symbol=row.get("benchmark_symbol"),
                relative_return=(
                    float(row["relative_return"]) if row.get("relative_return") is not None else None
                ),
                rank=(int(row["rank"]) if row.get("rank") is not None else None),
                sector=row.get("sector"),
                timestamp=(
                    pd.Timestamp(row["timestamp"])
                    if row.get("timestamp") is not None
                    else pd.Timestamp.now(tz="UTC")
                ),
                metadata=dict(row.get("metadata", {})),
            )
        )

    return MonitoringRunResult(
        scan_result=scan_result,
        regime_assessment=regime_assessment,
        relative_strength=rs_rows,
        warnings=list(payload.get("warnings", [])),
        errors=list(payload.get("errors", [])),
    )


def _resolve_symbols_from_inputs(args: argparse.Namespace) -> list[str]:
    loader = NSEUniverseLoader()
    if args.symbols:
        return loader.normalize_symbols(args.symbols)
    if args.symbols_file:
        return loader.get_custom_universe(args.symbols_file)
    return loader.get_universe(args.universe)


def _build_monitoring_from_symbols(
    *,
    symbols: list[str],
    provider_name: str,
    data_dir: str,
    timeframe: str,
    snapshot_top_n: int,
) -> MonitoringRunResult:
    scanner_cfg = ScannerConfig(
        universe_name="custom",
        provider_name=provider_name,
        data_dir=data_dir,
        timeframes=[timeframe],
        strategy_specs=[
            StrategyScanSpec(
                strategy_class=RSIReversionStrategy,
                params={"rsi_period": 14, "oversold": 30, "overbought": 70},
                timeframes=[timeframe],
            ),
            StrategyScanSpec(
                strategy_class=SMACrossoverStrategy,
                params={"fast_period": 20, "slow_period": 50},
                timeframes=[timeframe],
            ),
        ],
    )
    cfg = MonitoringConfig(
        scanner_config=scanner_cfg,
        watchlists=[WatchlistDefinition(name="operational", symbols=symbols)],
        regime=RegimeDetectorConfig(
            benchmark_symbol=symbols[0],
            timeframe=timeframe,
            use_benchmark=True,
            fallback_to_symbol=True,
        ),
        relative_strength=RelativeStrengthConfig(
            benchmark_symbol=symbols[0],
            timeframe=timeframe,
            allow_missing_benchmark=True,
        ),
        snapshot=SnapshotConfig(top_n=max(1, int(snapshot_top_n))),
    )
    monitor = MarketMonitor(config=cfg)
    return monitor.run(export=False, watchlist_names=["operational"])


def _write_summary(path: Path, *, profile: str, timeframe: str, input_source: str, result) -> None:
    lines = [
        "# Decision Runner Summary",
        "",
        f"- Generated at: {pd.Timestamp.now(tz='UTC').isoformat()}",
        f"- Profile: {profile}",
        f"- Timeframe: {timeframe}",
        f"- Input source: {input_source}",
        f"- Selected picks: {len(result.selected_picks)}",
        f"- Rejected opportunities: {len(result.rejected_opportunities)}",
        f"- Intraday picks: {len(result.top_intraday)}",
        f"- Swing picks: {len(result.top_swing)}",
        f"- Positional picks: {len(result.top_positional)}",
        "",
        "## Top Picks",
        "",
    ]
    if not result.selected_picks:
        lines.append("- No picks selected.")
    else:
        for pick in result.selected_picks[:10]:
            plan = pick.trade_plan
            lines.append(
                f"- `{plan.symbol}` `{plan.strategy_name}` horizon={plan.horizon.value} "
                f"conviction={pick.conviction_score:.2f} rr={plan.risk_reward:.2f}"
            )
    lines += [
        "",
        "## Safety",
        "- Decision runner is research-only.",
        "- No live broker order placement is performed.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_selected_json(result, output_path: Path) -> Path:
    payload = {
        "schema_version": "v1",
        "generated_at": result.generated_at.isoformat(),
        "source": "scripts.run_decision",
        "selected": [pick.to_dict() for pick in result.selected_picks],
    }
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    return output_path


def _write_rejected_json(result, output_path: Path) -> Path:
    payload = {
        "schema_version": "v1",
        "generated_at": result.generated_at.isoformat(),
        "source": "scripts.run_decision",
        "rejected": [row.to_dict() for row in result.rejected_opportunities],
    }
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    return output_path


def _write_candidates_csv(result, output_path: Path) -> Path:
    rows = [pick.to_dict() for pick in result.selected_picks]
    pd.DataFrame(rows).to_csv(output_path, index=False)
    return output_path


def _write_paper_handoff_csv(result, output_path: Path) -> Path:
    rows: list[dict[str, Any]] = []
    for pick in result.selected_picks:
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
    pd.DataFrame(rows).to_csv(output_path, index=False)
    return output_path


def main() -> int:
    args = parse_args()
    enforce_runtime_safety(
        RunMode.RESEARCH,
        explicit_enable_flag=True,
        execution_requested=False,
    )

    profile = get_runner_schedule_profile(args.profile)
    timeframe = _interval_to_timeframe(args.interval, profile.default_interval)
    validate_provider_for_mode(
        provider_name=args.provider,
        mode=RunMode.RESEARCH,
        timeframe=timeframe,
    )

    monitoring_input_dir = _resolve_monitoring_input_dir(args)
    input_source = "standalone"
    if monitoring_input_dir is not None:
        monitoring_result = _monitoring_result_from_artifacts(monitoring_input_dir)
        input_source = f"monitoring:{monitoring_input_dir}"
    else:
        symbols = _resolve_symbols_from_inputs(args)
        symbol_cap = int(args.max_symbols) if int(args.max_symbols) > 0 else int(profile.default_max_symbols)
        if symbol_cap > 0:
            symbols = symbols[:symbol_cap]
        if not symbols:
            raise ValueError("No symbols resolved for standalone decision run")
        monitoring_result = _build_monitoring_from_symbols(
            symbols=symbols,
            provider_name=args.provider,
            data_dir=args.data_dir,
            timeframe=timeframe,
            snapshot_top_n=profile.monitoring_top_picks,
        )

    decision_cfg = DecisionConfig()
    cap = int(profile.decision_max_picks_per_horizon)
    decision_cfg.thresholds.max_picks_by_horizon = {
        key: cap for key in decision_cfg.thresholds.max_picks_by_horizon
    }

    out_dir = resolve_runner_output_dir(
        output_dir=args.output_dir,
        runner_name="decision",
        timestamped=not bool(args.no_timestamped_output),
    )
    decision_cfg.export.output_dir = str(out_dir)

    result = PickEngine(decision_config=decision_cfg).run(monitoring_result=monitoring_result)
    exports = DecisionExporter().export_all(result, decision_cfg.export)
    result.exports = {name: str(path) for name, path in exports.items()}

    selected_json = _write_selected_json(result, out_dir / "decision_selected.json")
    rejected_json = _write_rejected_json(result, out_dir / "decision_rejected.json")
    candidates_csv = _write_candidates_csv(result, out_dir / "decision_candidates.csv")
    summary_md = out_dir / "decision_summary.md"
    _write_summary(summary_md, profile=args.profile, timeframe=timeframe, input_source=input_source, result=result)

    artifacts: dict[str, str | Path] = {
        "decision_candidates_csv": candidates_csv,
        "decision_selected_json": selected_json,
        "decision_rejected_json": rejected_json,
        "decision_summary_md": summary_md,
        "decision_summary_json": exports.get("summary_json", out_dir / "decision_summary.json"),
    }
    if args.paper_handoff:
        artifacts["paper_handoff_candidates"] = _write_paper_handoff_csv(
            result, out_dir / "paper_handoff_candidates.csv"
        )

    meta_path = write_runner_artifacts_meta(
        output_path=out_dir / "decision_artifacts_meta.json",
        runner_name="decision",
        profile=args.profile,
        provider=args.provider,
        interval=timeframe,
        execution_mode="research",
        source="scripts.run_decision",
        artifacts=artifacts,
        metadata={
            "input_source": input_source,
            "selected_total": len(result.selected_picks),
            "rejected_total": len(result.rejected_opportunities),
            "paper_handoff": bool(args.paper_handoff),
        },
    )
    artifacts["decision_artifacts_meta"] = meta_path
    artifacts["run_manifest"] = out_dir / "run_manifest.json"

    contract = get_artifact_contract_by_id("decision_runner_v1")
    manifest_path = write_output_manifest(
        output_dir=out_dir,
        run_mode=RunMode.RESEARCH,
        provider_name=args.provider,
        artifacts=artifacts,
        metadata={
            "runner_name": "decision",
            "profile": args.profile,
            "schema_version": "v1",
            "interval": timeframe,
            "execution_mode": "research",
            "input_source": input_source,
            "paper_handoff": bool(args.paper_handoff),
        },
        contract_id=contract.contract_id,
        expected_artifacts=contract.required_names,
        schema_version=contract.schema_version,
        safety_mode=contract.safety_mode,
    )
    assert_artifact_contract(
        contract_id=contract.contract_id,
        output_dir=out_dir,
        manifest_path=manifest_path,
    )

    print("DECISION RUN COMPLETE")
    print(f"  Output dir      : {out_dir}")
    print(f"  Profile         : {args.profile}")
    print(f"  Provider        : {args.provider}")
    print(f"  Timeframe       : {timeframe}")
    print(f"  Selected picks  : {len(result.selected_picks)}")
    print(f"  Rejected picks  : {len(result.rejected_opportunities)}")
    print(f"  Manifest        : {manifest_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RunnerArtifactResolutionError, FileNotFoundError, ValueError) as exc:
        print(f"Input resolution failed: {exc}")
        raise SystemExit(1) from exc
