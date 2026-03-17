#!/usr/bin/env python3
"""
Daily dry-run orchestration runner.

Runs scanner -> monitoring -> decision in a safe, non-live mode and validates
mid-pipeline artifact contracts.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.runtime import DailyDryRunConfig, DailyDryRunOrchestrator  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run daily dry-run orchestration.")
    parser.add_argument(
        "--output-dir",
        type=str,
        default="output/daily_dry_run",
        help="Output directory for stage artifacts and dry-run summary.",
    )
    parser.add_argument(
        "--provider",
        type=str,
        default="csv",
        help="Data provider name for scanner/monitoring stages.",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="data",
        help="Base data directory for CSV-style providers.",
    )
    parser.add_argument(
        "--symbols",
        nargs="*",
        default=["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS"],
        help="Symbol list for daily dry-run.",
    )
    parser.add_argument(
        "--symbols-limit",
        type=int,
        default=3,
        help="Limit symbols for safe daily dry-run.",
    )
    parser.add_argument(
        "--timeframe",
        type=str,
        default="1D",
        help="Canonical scanner timeframe (1m, 5m, 15m, 1h, 1D).",
    )
    parser.add_argument(
        "--no-paper-handoff",
        action="store_true",
        help="Disable writing paper_handoff_candidates.csv in decision stage.",
    )
    args = parser.parse_args()
    if args.symbols_limit < 1:
        parser.error("--symbols-limit must be >= 1")
    if not args.symbols:
        parser.error("--symbols must not be empty")
    return args


def main() -> int:
    args = parse_args()
    config = DailyDryRunConfig(
        output_dir=args.output_dir,
        provider_name=args.provider,
        data_dir=args.data_dir,
        symbols=args.symbols,
        symbols_limit=args.symbols_limit,
        timeframe=args.timeframe,
        include_paper_handoff=not bool(args.no_paper_handoff),
    )
    result = DailyDryRunOrchestrator(config=config).run()

    print("DAILY DRY-RUN COMPLETE")
    print(f"  Success       : {result.success}")
    print(f"  Provider      : {result.provider_name}")
    print(f"  Timeframe     : {result.timeframe}")
    print(f"  Symbols       : {', '.join(result.symbols)}")
    for stage in result.stages:
        print(f"  Stage {stage.stage_name:<10}: {'OK' if stage.success else 'FAIL'}")
        if stage.manifest_path:
            print(f"    Manifest    : {stage.manifest_path}")
        if stage.errors:
            for err in stage.errors:
                print(f"    Error       : {err}")

    if result.exports:
        print("  Outputs:")
        for key, value in sorted(result.exports.items()):
            print(f"    {key:<28} {value}")

    print("Safety note: this run does not place live broker orders.")
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
