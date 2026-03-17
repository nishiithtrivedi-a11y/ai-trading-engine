#!/usr/bin/env python3
"""
Standalone scanner operational runner.

Safe by default:
- research-only, no live execution
- deterministic artifact bundle with run manifest + metadata
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
from src.runtime import (  # noqa: E402
    RunMode,
    assert_artifact_contract,
    enforce_runtime_safety,
    get_artifact_contract_by_id,
    get_runner_schedule_profile,
    resolve_runner_output_dir,
    validate_provider_for_mode,
    validate_symbol_inputs,
    write_output_manifest,
    write_runner_artifacts_meta,
)
from src.scanners import (  # noqa: E402
    ScanExporter,
    ScannerConfig,
    StockScannerEngine,
    StrategyScanSpec,
    normalize_timeframe,
)
from src.strategies.breakout import BreakoutStrategy  # noqa: E402
from src.strategies.rsi_reversion import RSIReversionStrategy  # noqa: E402
from src.strategies.sma_crossover import SMACrossoverStrategy  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run standalone scanner workflow.")
    parser.add_argument("--provider", default="indian_csv", help="Provider name.")
    parser.add_argument("--symbols", nargs="*", default=None, help="Explicit symbol list.")
    parser.add_argument("--symbols-file", default="", help="CSV with symbol/ticker column.")
    parser.add_argument("--universe", default="nifty50", help="Universe name.")
    parser.add_argument(
        "--interval",
        default="",
        choices=["", "day", "5minute", "15minute", "60minute", "1D", "5m", "15m", "1h"],
        help="Scanner interval override.",
    )
    parser.add_argument(
        "--profile",
        default="morning",
        choices=["morning", "intraday", "eod"],
        help="Operational schedule profile.",
    )
    parser.add_argument("--output-dir", default="output/scanner", help="Output root directory.")
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="No-op for scanner runner; accepted for CLI consistency.",
    )
    parser.add_argument("--max-symbols", type=int, default=0, help="Optional max symbols.")
    parser.add_argument("--top-n", type=int, default=0, help="Optional top-N override.")
    parser.add_argument("--data-dir", default="data", help="CSV data directory.")
    parser.add_argument(
        "--strategies",
        nargs="+",
        choices=["rsi", "sma", "breakout"],
        default=["rsi", "sma"],
        help="Strategies to scan.",
    )
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
    if args.top_n < 0:
        parser.error("--top-n must be >= 0")
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


def _strategy_specs(selected: list[str], timeframe: str) -> list[StrategyScanSpec]:
    specs: list[StrategyScanSpec] = []
    for name in selected:
        if name == "rsi":
            specs.append(
                StrategyScanSpec(
                    strategy_class=RSIReversionStrategy,
                    params={"rsi_period": 14, "oversold": 30, "overbought": 70},
                    timeframes=[timeframe],
                )
            )
        elif name == "sma":
            specs.append(
                StrategyScanSpec(
                    strategy_class=SMACrossoverStrategy,
                    params={"fast_period": 20, "slow_period": 50},
                    timeframes=[timeframe],
                )
            )
        elif name == "breakout":
            specs.append(
                StrategyScanSpec(
                    strategy_class=BreakoutStrategy,
                    params={"entry_period": 20, "exit_period": 10},
                    timeframes=[timeframe],
                )
            )
    return specs


def _resolve_symbols(args: argparse.Namespace, loader: NSEUniverseLoader) -> list[str]:
    if args.symbols:
        symbols = loader.normalize_symbols(args.symbols)
    elif args.symbols_file:
        symbols = loader.get_custom_universe(args.symbols_file)
    else:
        symbols = loader.get_universe(args.universe)
    return symbols


def _write_summary(path: Path, *, symbols: list[str], timeframe: str, profile: str, result) -> None:
    lines = [
        "# Scanner Runner Summary",
        "",
        f"- Generated at: {pd.Timestamp.now(tz='UTC').isoformat()}",
        f"- Profile: {profile}",
        f"- Timeframe: {timeframe}",
        f"- Symbols requested: {len(symbols)}",
        f"- Symbols scanned: {result.num_symbols_scanned}",
        f"- Jobs: {result.num_jobs}",
        f"- Opportunities: {len(result.opportunities)}",
        f"- Errors: {result.num_errors}",
        "",
        "## Top Opportunities",
        "",
    ]
    top_df = result.to_dataframe(top_n=min(10, max(1, len(result.opportunities))))
    if top_df.empty:
        lines.append("- No actionable opportunities.")
    else:
        for _, row in top_df.iterrows():
            lines.append(
                f"- `{row.get('symbol')}` `{row.get('strategy_name')}` "
                f"timeframe={row.get('timeframe')} score={float(row.get('score', 0.0)):.2f}"
            )
    lines += [
        "",
        "## Safety",
        "- Research runner only.",
        "- No live broker order placement is performed.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


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

    out_dir = resolve_runner_output_dir(
        output_dir=args.output_dir,
        runner_name="scanner",
        timestamped=not bool(args.no_timestamped_output),
    )

    loader = NSEUniverseLoader()
    symbols = _resolve_symbols(args, loader)
    symbol_cap = int(args.max_symbols) if int(args.max_symbols) > 0 else int(profile.default_max_symbols)
    if symbol_cap > 0:
        symbols = symbols[:symbol_cap]
    if not symbols:
        raise ValueError("No symbols resolved for scanner run")

    universe_path = out_dir / "scanner_input_universe.csv"
    pd.DataFrame({"symbol": symbols}).to_csv(universe_path, index=False)

    top_n = int(args.top_n) if int(args.top_n) > 0 else int(profile.scanner_top_n)
    scanner_config = ScannerConfig(
        universe_name="custom",
        custom_universe_file=str(universe_path),
        provider_name=args.provider,
        data_dir=args.data_dir,
        timeframes=[timeframe],
        strategy_specs=_strategy_specs(args.strategies, timeframe),
        top_n=max(1, top_n),
    )
    engine = StockScannerEngine(scanner_config=scanner_config)
    result = engine.run(export=False)

    exporter = ScanExporter()
    csv_path = exporter.export_csv(result, out_dir / "scanner_candidates.csv", top_n=scanner_config.top_n)
    json_path = exporter.export_json(result, out_dir / "scanner_candidates.json", top_n=scanner_config.top_n)
    summary_path = out_dir / "scanner_summary.md"
    _write_summary(summary_path, symbols=symbols, timeframe=timeframe, profile=args.profile, result=result)

    contract = get_artifact_contract_by_id("scanner_runner_v1")
    artifacts: dict[str, str | Path] = {
        "scanner_candidates_csv": csv_path,
        "scanner_candidates_json": json_path,
        "scanner_summary_md": summary_path,
        "scanner_input_universe": universe_path,
    }
    meta_path = write_runner_artifacts_meta(
        output_path=out_dir / "scanner_artifacts_meta.json",
        runner_name="scanner",
        profile=args.profile,
        provider=args.provider,
        interval=timeframe,
        execution_mode="research",
        source="scripts.run_scanner",
        artifacts=artifacts,
        metadata={
            "symbols": symbols,
            "universe_source": ("symbols_file" if args.symbols_file else ("symbols" if args.symbols else args.universe)),
            "top_n": scanner_config.top_n,
            "strategies": list(args.strategies),
        },
    )
    artifacts["scanner_artifacts_meta"] = meta_path
    artifacts["run_manifest"] = out_dir / "run_manifest.json"

    manifest_path = write_output_manifest(
        output_dir=out_dir,
        run_mode=RunMode.RESEARCH,
        provider_name=args.provider,
        artifacts=artifacts,
        metadata={
            "runner_name": "scanner",
            "profile": args.profile,
            "schema_version": "v1",
            "symbols_count": len(symbols),
            "interval": timeframe,
            "execution_mode": "research",
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

    print("SCANNER RUN COMPLETE")
    print(f"  Output dir      : {out_dir}")
    print(f"  Profile         : {args.profile}")
    print(f"  Provider        : {args.provider}")
    print(f"  Timeframe       : {timeframe}")
    print(f"  Symbols scanned : {result.num_symbols_scanned}")
    print(f"  Opportunities   : {len(result.opportunities)}")
    print(f"  Manifest        : {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

