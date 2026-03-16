"""
Lightweight output manifest support for runner artifacts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd

from src.runtime.run_profiles import RunMode, get_run_profile


def _now_utc_iso() -> str:
    return pd.Timestamp.now(tz="UTC").isoformat()


@dataclass(frozen=True)
class OutputArtifact:
    name: str
    path: str

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "path": self.path}


@dataclass
class OutputManifest:
    schema_version: str
    run_mode: str
    provider_name: str
    contract_id: str | None = None
    expected_artifacts: list[str] = field(default_factory=list)
    safety_mode: str | None = None
    generated_at: str = field(default_factory=_now_utc_iso)
    artifacts: list[OutputArtifact] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    safety_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_mode": self.run_mode,
            "provider_name": self.provider_name,
            "contract_id": self.contract_id,
            "expected_artifacts": list(self.expected_artifacts),
            "safety_mode": self.safety_mode,
            "generated_at": self.generated_at,
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "metadata": dict(self.metadata),
            "safety_notes": list(self.safety_notes),
        }


def write_output_manifest(
    *,
    output_dir: str | Path,
    run_mode: RunMode | str,
    provider_name: str,
    artifacts: Mapping[str, str | Path] | Iterable[OutputArtifact],
    metadata: dict[str, Any] | None = None,
    schema_version: str = "1.0",
    filename: str = "run_manifest.json",
    contract_id: str | None = None,
    expected_artifacts: Iterable[str] | None = None,
    safety_mode: str | None = None,
) -> Path:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if isinstance(artifacts, Mapping):
        artifact_rows = [
            OutputArtifact(name=str(name), path=str(path))
            for name, path in artifacts.items()
        ]
    else:
        artifact_rows = list(artifacts)

    profile = get_run_profile(run_mode)
    manifest = OutputManifest(
        schema_version=schema_version,
        run_mode=profile.mode.value,
        provider_name=str(provider_name).strip().lower() or "unknown",
        contract_id=contract_id,
        expected_artifacts=sorted({str(name) for name in (expected_artifacts or [])}),
        safety_mode=safety_mode or "no_live_execution",
        artifacts=artifact_rows,
        metadata=dict(metadata or {}),
        safety_notes=list(profile.safety_notes),
    )
    manifest_path = out_dir / filename
    manifest_path.write_text(
        json.dumps(manifest.to_dict(), indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    return manifest_path
