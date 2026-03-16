"""
Artifact contract validation helpers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from src.runtime.artifact_contracts import ArtifactContract, get_artifact_contract
from src.runtime.run_profiles import RunMode


class ArtifactContractValidationError(RuntimeError):
    """Raised when an artifact bundle violates its contract."""


@dataclass
class ContractValidationResult:
    contract: ArtifactContract
    output_dir: Path
    manifest_path: Path | None
    produced_names: list[str] = field(default_factory=list)
    missing_required: list[str] = field(default_factory=list)
    missing_files: list[str] = field(default_factory=list)
    manifest_errors: list[str] = field(default_factory=list)
    unknown_artifacts: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        return not (
            self.missing_required
            or self.missing_files
            or self.manifest_errors
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract.contract_id,
            "run_mode": self.contract.run_mode.value,
            "output_dir": str(self.output_dir),
            "manifest_path": str(self.manifest_path) if self.manifest_path else None,
            "produced_names": list(self.produced_names),
            "missing_required": list(self.missing_required),
            "missing_files": list(self.missing_files),
            "manifest_errors": list(self.manifest_errors),
            "unknown_artifacts": list(self.unknown_artifacts),
            "details": dict(self.details),
            "is_valid": self.is_valid,
        }


def validate_artifact_contract(
    *,
    run_mode: RunMode | str,
    output_dir: str | Path,
    manifest_path: str | Path | None = None,
    require_manifest: bool = True,
    required_overrides: Iterable[str] | None = None,
) -> ContractValidationResult:
    contract = get_artifact_contract(run_mode)
    out_dir = Path(output_dir)
    manifest = Path(manifest_path) if manifest_path else (out_dir / "run_manifest.json")
    result = ContractValidationResult(
        contract=contract,
        output_dir=out_dir,
        manifest_path=manifest if manifest.exists() else None,
    )

    manifest_payload: dict[str, Any] = {}
    if require_manifest and not manifest.exists():
        result.manifest_errors.append(f"Missing manifest file: {manifest}")
    elif manifest.exists():
        try:
            manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            result.manifest_errors.append(f"Invalid manifest JSON: {exc}")
            manifest_payload = {}

    if manifest_payload:
        _validate_manifest_shape(contract, manifest_payload, result)
        artifact_map = _manifest_artifact_map(manifest_payload, out_dir)
    else:
        artifact_map = _scan_artifacts_from_directory(contract, out_dir)

    result.produced_names = sorted(artifact_map.keys())
    required_names = list(required_overrides) if required_overrides is not None else list(contract.required_names)

    for name in required_names:
        if name not in artifact_map:
            result.missing_required.append(name)

    for name, path in artifact_map.items():
        if not Path(path).exists():
            result.missing_files.append(f"{name}:{path}")

    known = set(contract.all_names)
    for name in artifact_map:
        if name not in known:
            result.unknown_artifacts.append(name)

    result.details["required_names"] = required_names
    result.details["optional_names"] = list(contract.optional_names)
    return result


def assert_artifact_contract(
    *,
    run_mode: RunMode | str,
    output_dir: str | Path,
    manifest_path: str | Path | None = None,
    require_manifest: bool = True,
    required_overrides: Iterable[str] | None = None,
) -> ContractValidationResult:
    result = validate_artifact_contract(
        run_mode=run_mode,
        output_dir=output_dir,
        manifest_path=manifest_path,
        require_manifest=require_manifest,
        required_overrides=required_overrides,
    )
    if not result.is_valid:
        raise ArtifactContractValidationError(
            f"Artifact contract validation failed for {result.contract.contract_id}: "
            f"{result.to_dict()}"
        )
    return result


def _validate_manifest_shape(
    contract: ArtifactContract,
    manifest_payload: Mapping[str, Any],
    result: ContractValidationResult,
) -> None:
    for field_name in contract.required_manifest_fields:
        if field_name not in manifest_payload:
            result.manifest_errors.append(f"Missing manifest field: {field_name}")

    if manifest_payload.get("run_mode") != contract.run_mode.value:
        result.manifest_errors.append(
            f"Manifest run_mode mismatch: expected={contract.run_mode.value} "
            f"actual={manifest_payload.get('run_mode')}"
        )
    if manifest_payload.get("schema_version") != contract.schema_version:
        result.manifest_errors.append(
            f"Manifest schema_version mismatch: expected={contract.schema_version} "
            f"actual={manifest_payload.get('schema_version')}"
        )
    if not str(manifest_payload.get("provider_name", "")).strip():
        result.manifest_errors.append("Manifest provider_name is empty")
    if not str(manifest_payload.get("generated_at", "")).strip():
        result.manifest_errors.append("Manifest generated_at is empty")

    contract_id = str(manifest_payload.get("contract_id", "")).strip()
    if contract_id and contract_id != contract.contract_id:
        result.manifest_errors.append(
            f"Manifest contract_id mismatch: expected={contract.contract_id} actual={contract_id}"
        )

    expected = manifest_payload.get("expected_artifacts")
    if isinstance(expected, list):
        expected_set = set(str(x) for x in expected)
        if not set(contract.required_names).issubset(expected_set):
            result.manifest_errors.append(
                "Manifest expected_artifacts missing one or more contract required artifacts"
            )


def _manifest_artifact_map(
    manifest_payload: Mapping[str, Any],
    output_dir: Path,
) -> dict[str, str]:
    artifact_rows = manifest_payload.get("artifacts", [])
    mapping: dict[str, str] = {}
    if not isinstance(artifact_rows, list):
        return mapping

    for row in artifact_rows:
        if not isinstance(row, Mapping):
            continue
        name = str(row.get("name", "")).strip()
        path_value = str(row.get("path", "")).strip()
        if not name or not path_value:
            continue
        candidate = Path(path_value)
        if not candidate.is_absolute():
            if candidate.exists():
                candidate = candidate.resolve()
            elif (output_dir / candidate).exists():
                candidate = output_dir / candidate
            else:
                # Keep unresolved fallback rooted at output_dir.
                candidate = output_dir / candidate
        mapping[name] = str(candidate)
    return mapping


def _scan_artifacts_from_directory(
    contract: ArtifactContract,
    output_dir: Path,
) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for spec in contract.required + contract.optional:
        candidate = output_dir / spec.filename
        if candidate.exists():
            mapping[spec.name] = str(candidate)
    return mapping
