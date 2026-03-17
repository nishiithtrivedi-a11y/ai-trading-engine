#!/usr/bin/env python3
"""
Standalone monitoring operational runner.

Supports:
- standalone monitoring runs
- scanner -> monitoring chaining via explicit scanner artifact directory
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from src.data.nse_universe import NSEUniverseLoader  # noqa: E402
from src.monitoring import (  # noqa: E402
    MonitoringConfig,
    MonitoringExportConfig,
    MarketMonitor,
    RegimeDetectorConfig,
    RelativeStrengthConfig,
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
from src.scanners import ScannerConfig, StrategyScanSpec, normalize_timeframe  # noqa: E402
from src.strategies.rsi_reversion import RSIReversionStrategy  # noqa: E402
from src.strategies.sma_crossover import SMACrossoverStrategy  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run standalone monitoring workflow.")
    parser.add_argument("--provider", default="indian_csv", help="Provider name.")
    parser.add_argument("--symbols", nargs="*", default=None, help="Explicit symbol list.")
    parser.add_argument("--symbols-file", default="", help="CSV with symbol/ticker column.")
    parser.add_argument("--universe", default="nifty50", help="Universe name.")
    parser.add_argument(
        "--interval",
        default="",
        choices=["", "day", "5minute", "15minute", "60minute", "1D", "5m", "15m", "1h"],
        help="Monitoring interval override.",
    )
    parser.add_argument(
        "--profile",
        default="intraday",
        choices=["morning", "intraday", "eod"],
        help="Operational schedule profile.",
    )
    parser.add_argument("--output-dir", default="output/monitoring", help="Output root directory.")
    parser.add_argument(
        "--scanner-input-dir",
        "--input-dir",
        dest="scanner_input_dir",
        default="",
        help="Optional scanner artifact directory for chained monitoring.",
    )
    parser.add_argument(
        "--use-latest-scanner-input",
        action="store_true",
        help="Resolve latest scanner run under output/scanner when scanner input is omitted.",
    )
    parser.add_argument("--run-once", action="store_true", help="No-op; accepted for CLI consistency.")
    parser.add_argument("--max-symbols", type=int, default=0, help="Optional max symbols.")
    parser.add_argument("--data-dir", default="data", help="CSV data directory.")
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


def _resolve_symbols_from_inputs(args: argparse.Namespace) -> list[str]:
    loader = NSEUniverseLoader()
    if args.symbols:
        return loader.normalize_symbols(args.symbols)
    if args.symbols_file:
        return loader.get_custom_universe(args.symbols_file)
    return loader.get_universe(args.universe)


def _resolve_scanner_input_dir(args: argparse.Namespace) -> Path | None:
    if args.scanner_input_dir:
        return Path(args.scanner_input_dir)
    if args.use_latest_scanner_input:
        return resolve_latest_runner_dir(output_dir="output/scanner")
    return None


def _resolve_symbols_from_scanner_artifacts(scanner_dir: Path) -> list[str]:
    if not scanner_dir.exists():
        raise FileNotFoundError(f"scanner input directory not found: {scanner_dir}")

    candidates_json = scanner_dir / "scanner_candidates.json"
    if candidates_json.exists():
        payload = load_json_file(candidates_json)
        opportunities = payload.get("opportunities", []) if isinstance(payload, dict) else []
        symbols = [
            str(row.get("symbol", "")).strip().upper()
            for row in opportunities
            if isinstance(row, dict) and str(row.get("symbol", "")).strip()
        ]
        if symbols:
            return list(dict.fromkeys(symbols))

    universe_csv = scanner_dir / "scanner_input_universe.csv"
    if universe_csv.exists():
        df = pd.read_csv(universe_csv)
        if "symbol" not in df.columns:
            raise ValueError(
                f"scanner_input_universe.csv in {scanner_dir} does not contain a 'symbol' column"
            )
        rows = [str(sym).strip().upper() for sym in df["symbol"].dropna().astype(str).tolist()]
        rows = [sym for sym in rows if sym]
        if rows:
            return list(dict.fromkeys(rows))

    raise FileNotFoundError(
        f"No usable scanner symbol artifact found in {scanner_dir} "
        "(expected scanner_candidates.json and/or scanner_input_universe.csv)"
    )


def _write_summary(path: Path, *, profile: str, timeframe: str, symbols: list[str], result) -> None:
    lines = [
        "# Monitoring Runner Summary",
        "",
        f"- Generated at: {pd.Timestamp.now(tz='UTC').isoformat()}",
        f"- Profile: {profile}",
        f"- Timeframe: {timeframe}",
        f"- Symbols requested: {len(symbols)}",
        f"- Alerts: {len(result.alerts)}",
        f"- Relative-strength rows: {len(result.relative_strength)}",
        f"- Top picks: {len(result.snapshot.top_picks) if result.snapshot else 0}",
        f"- Warnings: {len(result.warnings)}",
        f"- Errors: {len(result.errors)}",
        "",
        "## Top Picks",
        "",
    ]
    picks = result.snapshot.top_picks if result.snapshot else []
    if not picks:
        lines.append("- No top picks were generated.")
    else:
        for pick in picks[:10]:
            lines.append(
                f"- `{pick.symbol}` `{pick.strategy_name}` timeframe={pick.timeframe} score={float(pick.score):.2f}"
            )
    lines += [
        "",
        "## Safety",
        "- Monitoring runner only.",
        "- No live broker order placement is performed.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _build_monitoring_decision_input(result, output_path: Path) -> Path:
    payload: dict[str, Any] = {
        "schema_version": "v1",
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "source": "scripts.run_monitoring",
        "scan_result": result.scan_result.to_dict() if result.scan_result else {},
        "regime_assessment": result.regime_assessment.to_dict() if result.regime_assessment else None,
        "relative_strength": [row.to_dict() for row in result.relative_strength],
        "warnings": list(result.warnings),
        "errors": list(result.errors),
    }
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
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

    scanner_input_dir = _resolve_scanner_input_dir(args)
    if scanner_input_dir is not None:
        symbols = _resolve_symbols_from_scanner_artifacts(scanner_input_dir)
        universe_source = f"scanner:{scanner_input_dir}"
    else:
        symbols = _resolve_symbols_from_inputs(args)
        universe_source = "symbols" if args.symbols else ("symbols_file" if args.symbols_file else args.universe)

    symbol_cap = int(args.max_symbols) if int(args.max_symbols) > 0 else int(profile.default_max_symbols)
    if symbol_cap > 0:
        symbols = symbols[:symbol_cap]
    if not symbols:
        raise ValueError("No symbols resolved for monitoring run")

    out_dir = resolve_runner_output_dir(
        output_dir=args.output_dir,
        runner_name="monitoring",
        timestamped=not bool(args.no_timestamped_output),
    )

    scanner_cfg = ScannerConfig(
        universe_name="custom",
        provider_name=args.provider,
        data_dir=args.data_dir,
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

    monitoring_cfg = MonitoringConfig(
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
        snapshot=SnapshotConfig(top_n=max(1, int(profile.monitoring_top_picks))),
        export=MonitoringExportConfig(
            output_dir=str(out_dir),
            write_csv=True,
            write_json=True,
            alerts_csv_filename="alerts.csv",
            alerts_json_filename="alerts.json",
            top_picks_csv_filename="monitored_setups.csv",
            market_snapshot_json_filename="monitored_setups.json",
            relative_strength_csv_filename="relative_strength.csv",
            relative_strength_json_filename="relative_strength.json",
            regime_summary_json_filename="regime_summary.json",
            manifest_json_filename="monitoring_run_manifest.json",
        ),
    )

    monitor = MarketMonitor(config=monitoring_cfg)
    result = monitor.run(export=True, watchlist_names=["operational"])

    summary_path = out_dir / "monitoring_summary.md"
    _write_summary(summary_path, profile=args.profile, timeframe=timeframe, symbols=symbols, result=result)
    decision_input_path = _build_monitoring_decision_input(result, out_dir / "monitoring_decision_input.json")

    artifacts: dict[str, str | Path] = {
        "monitored_setups_csv": out_dir / "monitored_setups.csv",
        "monitored_setups_json": out_dir / "monitored_setups.json",
        "monitoring_summary_md": summary_path,
        "monitoring_decision_input": decision_input_path,
        "alerts_csv": out_dir / "alerts.csv",
        "alerts_json": out_dir / "alerts.json",
        "relative_strength_csv": out_dir / "relative_strength.csv",
        "regime_summary_json": out_dir / "regime_summary.json",
    }
    meta_path = write_runner_artifacts_meta(
        output_path=out_dir / "monitoring_artifacts_meta.json",
        runner_name="monitoring",
        profile=args.profile,
        provider=args.provider,
        interval=timeframe,
        execution_mode="research",
        source="scripts.run_monitoring",
        artifacts=artifacts,
        metadata={
            "symbols": symbols,
            "universe_source": universe_source,
            "scanner_input_dir": str(scanner_input_dir) if scanner_input_dir else "",
            "alerts": len(result.alerts),
            "top_picks": len(result.snapshot.top_picks) if result.snapshot else 0,
        },
    )
    artifacts["monitoring_artifacts_meta"] = meta_path
    artifacts["run_manifest"] = out_dir / "run_manifest.json"

    contract = get_artifact_contract_by_id("monitoring_runner_v1")
    manifest_path = write_output_manifest(
        output_dir=out_dir,
        run_mode=RunMode.RESEARCH,
        provider_name=args.provider,
        artifacts=artifacts,
        metadata={
            "runner_name": "monitoring",
            "profile": args.profile,
            "schema_version": "v1",
            "interval": timeframe,
            "symbols_count": len(symbols),
            "execution_mode": "research",
            "scanner_input_dir": str(scanner_input_dir) if scanner_input_dir else "",
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

    print("MONITORING RUN COMPLETE")
    print(f"  Output dir    : {out_dir}")
    print(f"  Profile       : {args.profile}")
    print(f"  Provider      : {args.provider}")
    print(f"  Timeframe     : {timeframe}")
    print(f"  Symbols       : {len(symbols)}")
    print(f"  Top picks     : {len(result.snapshot.top_picks) if result.snapshot else 0}")
    print(f"  Manifest      : {manifest_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RunnerArtifactResolutionError, FileNotFoundError, ValueError) as exc:
        print(f"Input resolution failed: {exc}")
        raise SystemExit(1) from exc
