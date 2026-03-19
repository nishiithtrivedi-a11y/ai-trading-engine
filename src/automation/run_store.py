"""
File-based JSON persistence for automation run history.

Stores run records as individual JSON files in a configurable directory.
Supports querying recent runs, runs by job, and single run lookups.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from src.automation.models import RunRecord


@dataclass
class RunStore:
    """Persist and query automation run records."""

    store_dir: Path = field(default_factory=lambda: Path("output/automation/runs"))
    max_history: int = 500

    def __post_init__(self) -> None:
        self.store_dir = Path(self.store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)

    def save_run(self, record: RunRecord) -> Path:
        """Persist a run record to disk."""
        path = self.store_dir / f"{record.run_id}.json"
        path.write_text(
            json.dumps(record.to_dict(), indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
        self._enforce_retention()
        return path

    def get_run(self, run_id: str) -> Optional[RunRecord]:
        """Load a single run record by ID."""
        path = self.store_dir / f"{run_id}.json"
        if not path.exists():
            return None
        return self._load_record(path)

    def get_recent_runs(self, limit: int = 50) -> list[RunRecord]:
        """Return the most recent run records, newest first."""
        files = sorted(
            self.store_dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        records: list[RunRecord] = []
        for path in files[:limit]:
            record = self._load_record(path)
            if record is not None:
                records.append(record)
        return records

    def get_runs_by_job(self, job_id: str, limit: int = 20) -> list[RunRecord]:
        """Return recent runs for a specific job, newest first."""
        all_runs = self.get_recent_runs(limit=self.max_history)
        matching = [r for r in all_runs if r.job_id == job_id]
        return matching[:limit]

    def _load_record(self, path: Path) -> Optional[RunRecord]:
        """Load a RunRecord from a JSON file."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return RunRecord(
                run_id=data.get("run_id", ""),
                job_id=data.get("job_id", ""),
                pipeline_type=data.get("pipeline_type", ""),
                trigger_source=data.get("trigger_source", "manual_ui"),
                status=data.get("status", "queued"),
                execution_mode=data.get("execution_mode", "research"),
                market_phase=data.get("market_phase", "unknown"),
                runtime_source=data.get("runtime_source", "csv"),
                started_at=data.get("started_at", ""),
                completed_at=data.get("completed_at"),
                duration_seconds=data.get("duration_seconds"),
                linked_artifacts=data.get("linked_artifacts", []),
                manifest_path=data.get("manifest_path"),
                error_message=data.get("error_message"),
                error_details=data.get("error_details"),
                metadata=data.get("metadata", {}),
            )
        except (json.JSONDecodeError, KeyError, TypeError):
            return None

    def _enforce_retention(self) -> None:
        """Remove oldest records if store exceeds max_history."""
        files = sorted(
            self.store_dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
        )
        excess = len(files) - self.max_history
        if excess > 0:
            for path in files[:excess]:
                path.unlink(missing_ok=True)
