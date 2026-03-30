#!/usr/bin/env python3
"""
Provider runtime readiness diagnostics.

Examples:
  python scripts/check_provider_readiness.py --provider zerodha
  python scripts/check_provider_readiness.py --all
  python scripts/check_provider_readiness.py --all --mode research --timeframe 5m
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
except Exception:
    pass

from src.data.provider_runtime import (  # noqa: E402
    get_provider_readiness_report,
    list_all_provider_reports,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check provider runtime readiness.")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--provider", type=str, help="Single provider name (e.g. zerodha).")
    target.add_argument("--all", action="store_true", help="Report all configured providers.")
    parser.add_argument(
        "--mode",
        type=str,
        default="",
        help="Optional workflow mode hint (research, paper, live_safe).",
    )
    parser.add_argument(
        "--timeframe",
        type=str,
        default="",
        help="Optional timeframe hint (1D, 5m, 15m, 1h).",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    return parser.parse_args()


def _report_to_payload(report: Any) -> dict[str, Any]:
    payload = report.to_dict()
    # Defensive: never include raw secrets if future fields are added.
    payload.pop("credentials_values", None)
    return payload


def _print_human_report(report: Any) -> None:
    payload = _report_to_payload(report)
    print("-" * 72)
    print(f"Provider: {payload['provider_name']} ({payload['display_name']})")
    print(f"State: {payload['state']}")
    print(f"Reason: {payload['reason']}")
    print(
        "Enabled: {enabled} | Default: {default} | Can Instantiate: {inst}".format(
            enabled=payload["enabled"],
            default=payload["is_default_provider"],
            inst=payload["can_instantiate"],
        )
    )
    print(
        "Session Required: {req} | Session Status: {status}".format(
            req=payload["requires_session"],
            status=payload["session_status"] or "n/a",
        )
    )
    print(f"Workflow Supported: {payload['workflow_supported']}")
    if payload["credentials_required"]:
        print("Credentials:")
        for credential_name in payload["credentials_required"]:
            present = payload["credentials_present"].get(credential_name, False)
            env_keys = payload["credential_env_keys"].get(credential_name, [])
            missing = "*" if credential_name in payload["missing_credentials"] else ""
            print(
                f"  - {credential_name}: present={present}{missing} env_keys={','.join(env_keys)}"
            )
    else:
        print("Credentials: none required")


def main() -> int:
    args = parse_args()
    mode = str(args.mode).strip().lower() or None
    timeframe = str(args.timeframe).strip() or None

    if args.provider:
        report = get_provider_readiness_report(
            args.provider,
            mode=mode,
            timeframe=timeframe,
            require_enabled=False,
        )
        if args.json:
            print(json.dumps(_report_to_payload(report), indent=2, ensure_ascii=True))
        else:
            _print_human_report(report)
        return 0

    reports = list_all_provider_reports(
        mode=mode,
        timeframe=timeframe,
        require_enabled=False,
    )
    payload = [_report_to_payload(report) for report in reports]
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=True))
        return 0

    for report in reports:
        _print_human_report(report)
    print("-" * 72)
    print(f"Total providers: {len(reports)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

