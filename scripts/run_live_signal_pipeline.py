#!/usr/bin/env python3
"""
Live-safe market data and signal pipeline runner.

Safety defaults:
- no action unless --live-signals is explicitly provided
- single run by default (no infinite loop)
- generates signals/artifacts only; no live order placement
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.live import (  # noqa: E402
    LiveSignalPipeline,
    LiveSignalPipelineConfig,
    load_regime_policy_if_available,
)
from src.runtime import (  # noqa: E402
    RunMode,
    RunnerValidationError,
    assert_artifact_contract,
    enforce_runtime_safety,
    get_artifact_contract,
    validate_polling_inputs,
    validate_provider_for_mode,
    validate_symbol_inputs,
    write_output_manifest,
)
from src.strategies.breakout import BreakoutStrategy  # noqa: E402
from src.strategies.rsi_reversion import RSIReversionStrategy  # noqa: E402
from src.strategies.sma_crossover import SMACrossoverStrategy  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the live-safe signal pipeline.")

    parser.add_argument("--live-signals", action="store_true", help="Explicitly enable live signal pipeline")
    parser.add_argument("--provider", default="indian_csv", help="Provider name (csv, indian_csv, zerodha, upstox)")
    parser.add_argument("--universe", default="nifty50", help="Universe name (nifty50, banknifty, nifty_next_50, custom)")
    parser.add_argument("--symbols", nargs="*", default=None, help="Explicit symbol list override")
    parser.add_argument("--symbols-limit", type=int, default=5, help="Limit symbols for safe runs")
    parser.add_argument("--interval", default="day", choices=["day", "5minute", "15minute", "60minute"], help="Bar interval")
    parser.add_argument("--lookback-bars", type=int, default=250, help="Bars to retain per symbol")
    parser.add_argument("--output-dir", default="output/live_signals", help="Output directory for artifacts")
    parser.add_argument("--top-n-symbols", type=int, default=0, help="Keep top N by relative strength; 0 keeps all")
    parser.add_argument("--benchmark-symbol", default="", help="Optional benchmark symbol for relative strength")
    parser.add_argument("--regime-policy-json", default="", help="Optional regime policy JSON path")
    parser.add_argument("--paper-handoff", action="store_true", help="Write paper_handoff_signals.csv")
    parser.add_argument("--session-label", default="", help="Optional run label")
    parser.add_argument("--run-once", action="store_true", help="Force a single pipeline cycle")
    parser.add_argument("--poll-seconds", type=int, default=0, help="Optional polling interval in seconds")
    parser.add_argument("--max-cycles", type=int, default=3, help="Max cycles when polling is enabled")
    parser.add_argument(
        "--strategies",
        nargs="+",
        choices=["sma", "rsi", "breakout"],
        default=["sma", "rsi", "breakout"],
        help="Available strategy set for signal generation",
    )

    args = parser.parse_args()
    try:
        if args.symbols_limit < 0:
            raise RunnerValidationError("--symbols-limit must be >= 0")
        if args.lookback_bars < 2:
            raise RunnerValidationError("--lookback-bars must be >= 2")
        if args.top_n_symbols < 0:
            raise RunnerValidationError("--top-n-symbols must be >= 0")
        validate_symbol_inputs(
            symbols=args.symbols,
            universe=args.universe,
            universe_file=None,
        )
        validate_polling_inputs(
            run_once=bool(args.run_once),
            poll_seconds=args.poll_seconds,
            max_cycles=args.max_cycles,
        )
    except RunnerValidationError as exc:
        parser.error(str(exc))
    return args


def build_strategy_registry(selected: list[str]) -> dict[str, dict[str, Any]]:
    all_strategies: dict[str, dict[str, Any]] = {
        "sma": {
            "class": SMACrossoverStrategy,
            "params": {"fast_period": 20, "slow_period": 50},
        },
        "rsi": {
            "class": RSIReversionStrategy,
            "params": {"rsi_period": 14, "oversold": 30, "overbought": 70},
        },
        "breakout": {
            "class": BreakoutStrategy,
            "params": {"entry_period": 20, "exit_period": 10},
        },
    }
    return {name: all_strategies[name] for name in selected}


def print_cycle_summary(cycle_num: int, report) -> None:
    summary = report.to_dict()["summary"]
    print(f"LIVE SIGNAL CYCLE {cycle_num} COMPLETE")
    print(f"  Provider                : {report.provider_name}")
    print(f"  Timeframe               : {report.timeframe}")
    print(f"  Symbols loaded          : {summary['symbols_loaded']}")
    print(f"  Actionable signals      : {summary['actionable_signals']}")
    print(f"  No-trade decisions      : {summary['no_trade_decisions']}")
    print(f"  Risk rejections         : {summary['risk_rejections']}")
    print(f"  Paper-handoff eligible  : {summary['paper_handoff_eligible']}")
    if report.exports:
        print("  Artifacts:")
        for key, path in sorted(report.exports.items()):
            print(f"    {key:<16} {path}")
    if report.warnings:
        print("  Warnings:")
        for warning in report.warnings:
            print(f"    - {warning}")
    if report.errors:
        print("  Errors:")
        for error in report.errors:
            print(f"    - {error}")


def main() -> int:
    args = parse_args()

    if not args.live_signals:
        try:
            enforce_runtime_safety(
                RunMode.LIVE_SAFE,
                explicit_enable_flag=False,
                execution_requested=False,
            )
        except Exception as exc:  # noqa: BLE001
            print(str(exc))
        return 0

    enforce_runtime_safety(
        RunMode.LIVE_SAFE,
        explicit_enable_flag=True,
        execution_requested=False,
    )

    timeframe_map = {
        "day": "1D",
        "5minute": "5m",
        "15minute": "15m",
        "60minute": "1h",
    }
    timeframe = timeframe_map[str(args.interval).strip().lower()]
    try:
        validate_provider_for_mode(
            provider_name=args.provider,
            mode=RunMode.LIVE_SAFE,
            timeframe=timeframe,
        )
    except RunnerValidationError as exc:
        print(f"Provider validation failed: {exc}")
        return 1

    regime_policy = load_regime_policy_if_available(args.regime_policy_json)
    if args.regime_policy_json and regime_policy is None:
        print(f"Warning: regime policy not loaded from '{args.regime_policy_json}'. Proceeding without regime policy.")

    config = LiveSignalPipelineConfig(
        enabled=True,
        provider_name=args.provider,
        universe_name=args.universe,
        symbols=args.symbols or [],
        symbols_limit=args.symbols_limit,
        interval=args.interval,
        lookback_bars=args.lookback_bars,
        output_dir=args.output_dir,
        top_n_symbols=args.top_n_symbols,
        benchmark_symbol=(args.benchmark_symbol or None),
        session_label=args.session_label,
        paper_handoff=bool(args.paper_handoff),
    )

    pipeline = LiveSignalPipeline(
        config=config,
        strategy_registry=build_strategy_registry(args.strategies),
        regime_policy=regime_policy,
    )

    run_once = bool(args.run_once or args.poll_seconds <= 0)
    cycle_count = 1 if run_once else max(1, int(args.max_cycles))

    for cycle in range(1, cycle_count + 1):
        report = pipeline.run()
        if report.exports:
            contract = get_artifact_contract(RunMode.LIVE_SAFE)
            manifest_artifacts = dict(report.exports)
            manifest_artifacts["run_manifest"] = Path(args.output_dir) / "run_manifest.json"
            manifest_path = write_output_manifest(
                output_dir=args.output_dir,
                run_mode=RunMode.LIVE_SAFE,
                provider_name=args.provider,
                artifacts=manifest_artifacts,
                metadata={
                    "cycle": cycle,
                    "poll_seconds": args.poll_seconds,
                    "run_once": bool(run_once),
                    "paper_handoff": bool(args.paper_handoff),
                    "symbols_loaded": report.to_dict()["summary"]["symbols_loaded"],
                },
                contract_id=contract.contract_id,
                expected_artifacts=contract.required_names,
                schema_version=contract.schema_version,
                safety_mode=contract.safety_mode,
            )
            report.exports["run_manifest"] = str(manifest_path)
            required_overrides = (
                contract.required_names + ("paper_handoff",)
                if args.paper_handoff
                else None
            )
            try:
                assert_artifact_contract(
                    run_mode=RunMode.LIVE_SAFE,
                    output_dir=args.output_dir,
                    manifest_path=manifest_path,
                    required_overrides=required_overrides,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"Artifact contract validation failed: {exc}")
                return 1
        print_cycle_summary(cycle, report)

        if run_once or cycle == cycle_count:
            break

        sleep_seconds = max(1, int(args.poll_seconds))
        time.sleep(sleep_seconds)

    print("Safety note: no live broker orders were placed in this run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
