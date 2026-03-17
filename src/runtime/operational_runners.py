"""
Operational runner helpers for scanner/monitoring/decision scripts.

These helpers keep standalone runners consistent without introducing a heavy
automation framework.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping


RUNNER_ARTIFACT_SCHEMA_VERSION = "v1"


class RunnerProfileName(str, Enum):
    MORNING = "morning"
    INTRADAY = "intraday"
    EOD = "eod"


class RunnerArtifactResolutionError(RuntimeError):
    """Raised when latest-run/artifact resolution cannot be completed safely."""


@dataclass(frozen=True)
class RunnerScheduleProfile:
    name: RunnerProfileName
    default_interval: str
    default_max_symbols: int
    scanner_top_n: int
    monitoring_top_picks: int
    decision_max_picks_per_horizon: int
    description: str


_PROFILES: dict[RunnerProfileName, RunnerScheduleProfile] = {
    RunnerProfileName.MORNING: RunnerScheduleProfile(
        name=RunnerProfileName.MORNING,
        default_interval="day",
        default_max_symbols=50,
        scanner_top_n=50,
        monitoring_top_picks=20,
        decision_max_picks_per_horizon=7,
        description="Broad morning opportunity discovery for session planning.",
    ),
    RunnerProfileName.INTRADAY: RunnerScheduleProfile(
        name=RunnerProfileName.INTRADAY,
        default_interval="5minute",
        default_max_symbols=20,
        scanner_top_n=20,
        monitoring_top_picks=10,
        decision_max_picks_per_horizon=4,
        description="Focused intraday refresh with tighter symbol/watchlist scope.",
    ),
    RunnerProfileName.EOD: RunnerScheduleProfile(
        name=RunnerProfileName.EOD,
        default_interval="day",
        default_max_symbols=30,
        scanner_top_n=30,
        monitoring_top_picks=15,
        decision_max_picks_per_horizon=6,
        description="End-of-day consolidation and next-session planning snapshot.",
    ),
}


def get_runner_schedule_profile(
    profile: RunnerProfileName | str,
) -> RunnerScheduleProfile:
    if isinstance(profile, RunnerProfileName):
        key = profile
    else:
        key = RunnerProfileName(str(profile).strip().lower())
    return _PROFILES[key]


def utc_timestamp_slug(now: datetime | None = None) -> str:
    timestamp = now or datetime.now(timezone.utc)
    return timestamp.strftime("%Y%m%dT%H%M%SZ")


def resolve_runner_output_dir(
    *,
    output_dir: str | Path,
    runner_name: str,
    timestamped: bool = True,
) -> Path:
    base = Path(output_dir)
    target = base / utc_timestamp_slug() if timestamped else base
    target.mkdir(parents=True, exist_ok=True)
    (target / ".runner").write_text(str(runner_name), encoding="utf-8")
    return target


def resolve_latest_runner_dir(
    *,
    output_dir: str | Path,
    require_manifest: bool = True,
) -> Path:
    base = Path(output_dir)
    if not base.exists():
        raise RunnerArtifactResolutionError(f"Output directory does not exist: {base}")
    if not base.is_dir():
        raise RunnerArtifactResolutionError(f"Output path is not a directory: {base}")

    candidates = [child for child in base.iterdir() if child.is_dir()]
    if require_manifest:
        candidates = [child for child in candidates if (child / "run_manifest.json").exists()]

    if not candidates:
        requirement = " with run_manifest.json" if require_manifest else ""
        raise RunnerArtifactResolutionError(
            f"No run directories found under {base}{requirement}"
        )

    return max(candidates, key=lambda path: path.stat().st_mtime)


def write_runner_artifacts_meta(
    *,
    output_path: str | Path,
    runner_name: str,
    profile: RunnerProfileName | str,
    provider: str,
    interval: str,
    execution_mode: str,
    source: str,
    artifacts: Mapping[str, str | Path],
    metadata: Mapping[str, Any] | None = None,
) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    profile_name = (
        profile.value if isinstance(profile, RunnerProfileName) else str(profile).strip().lower()
    )
    payload = {
        "schema_version": RUNNER_ARTIFACT_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "runner_name": runner_name,
        "profile": profile_name,
        "provider": str(provider).strip().lower(),
        "interval": str(interval).strip(),
        "execution_mode": str(execution_mode).strip().lower(),
        "artifacts": {
            name: {
                "path": str(path),
                "format": Path(path).suffix.lstrip(".").lower(),
            }
            for name, path in artifacts.items()
        },
        "metadata": dict(metadata or {}),
    }
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    return target


def load_json_file(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))

