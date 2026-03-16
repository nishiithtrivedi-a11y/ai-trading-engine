from __future__ import annotations

from pathlib import Path

import pytest

from src.runtime.artifact_contracts import get_artifact_contract
from src.runtime.contract_validation import (
    ArtifactContractValidationError,
    assert_artifact_contract,
    validate_artifact_contract,
)
from src.runtime.output_manifest import write_output_manifest


def _write_artifact(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix in {".csv", ".md"}:
        path.write_text("x", encoding="utf-8")
    else:
        path.write_text("{}", encoding="utf-8")


def _build_contract_bundle(tmp_path: Path, mode: str) -> Path:
    contract = get_artifact_contract(mode)
    artifacts: dict[str, Path] = {}
    for spec in contract.required:
        target = tmp_path / spec.filename
        if spec.name != "run_manifest":
            _write_artifact(target)
        artifacts[spec.name] = target

    manifest_path = write_output_manifest(
        output_dir=tmp_path,
        run_mode=contract.run_mode,
        provider_name="indian_csv",
        artifacts=artifacts,
        metadata={"test_mode": mode},
        contract_id=contract.contract_id,
        expected_artifacts=contract.required_names,
        schema_version=contract.schema_version,
        safety_mode=contract.safety_mode,
    )
    return manifest_path


def test_validate_contract_success_for_paper_bundle(tmp_path: Path) -> None:
    manifest_path = _build_contract_bundle(tmp_path, "paper")
    result = validate_artifact_contract(
        run_mode="paper",
        output_dir=tmp_path,
        manifest_path=manifest_path,
    )
    assert result.is_valid is True
    assert result.missing_required == []
    assert result.manifest_errors == []


def test_validate_contract_detects_missing_required_artifact(tmp_path: Path) -> None:
    manifest_path = _build_contract_bundle(tmp_path, "live_safe")
    (tmp_path / "signals.csv").unlink(missing_ok=True)
    result = validate_artifact_contract(
        run_mode="live_safe",
        output_dir=tmp_path,
        manifest_path=manifest_path,
    )
    assert result.is_valid is False
    assert "signals:{}".format(tmp_path / "signals.csv") in result.missing_files


def test_validate_contract_detects_manifest_run_mode_mismatch(tmp_path: Path) -> None:
    # Build live-safe files but intentionally write a paper-mode manifest.
    live_contract = get_artifact_contract("live_safe")
    artifacts: dict[str, Path] = {}
    for spec in live_contract.required:
        target = tmp_path / spec.filename
        if spec.name != "run_manifest":
            _write_artifact(target)
        artifacts[spec.name] = target

    manifest_path = write_output_manifest(
        output_dir=tmp_path,
        run_mode="paper",
        provider_name="indian_csv",
        artifacts=artifacts,
    )
    result = validate_artifact_contract(
        run_mode="live_safe",
        output_dir=tmp_path,
        manifest_path=manifest_path,
    )
    assert result.is_valid is False
    assert any("run_mode mismatch" in err for err in result.manifest_errors)


def test_assert_contract_raises_for_invalid_bundle(tmp_path: Path) -> None:
    with pytest.raises(ArtifactContractValidationError):
        assert_artifact_contract(run_mode="paper", output_dir=tmp_path)
