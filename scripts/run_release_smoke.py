#!/usr/bin/env python3
"""
Release smoke workflow runner.

Runs minimal research/paper/live-safe workflows and validates produced
artifact bundles via runtime contracts.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.runtime.workflow_orchestrator import WorkflowOrchestrator  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run release smoke workflows.")
    parser.add_argument(
        "--output-dir",
        type=str,
        default="output/release_smoke",
        help="Output root for smoke workflow artifacts.",
    )
    parser.add_argument(
        "--symbols-limit",
        type=int,
        default=3,
        help="Research symbols limit for smoke path.",
    )
    args = parser.parse_args()
    if args.symbols_limit < 1:
        parser.error("--symbols-limit must be >= 1")
    return args


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    orchestrator = WorkflowOrchestrator(root_dir=ROOT)
    results = orchestrator.run_release_smoke(
        output_root=output_dir,
        symbols_limit=args.symbols_limit,
    )

    all_success = True
    payload: dict[str, object] = {}
    for workflow_name, result in results.items():
        payload[workflow_name] = result.to_dict()
        if result.success:
            print(f"[OK] {workflow_name}")
        else:
            print(f"[FAIL] {workflow_name}")
            for error in result.errors:
                print(f"  - {error}")
            all_success = False

    summary_path = output_dir / "release_smoke_summary.json"
    summary_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    print(f"Summary: {summary_path}")

    return 0 if all_success else 1


if __name__ == "__main__":
    raise SystemExit(main())
