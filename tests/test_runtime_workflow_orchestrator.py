from __future__ import annotations

import subprocess
from pathlib import Path

from src.runtime.artifact_contracts import get_artifact_contract
from src.runtime.output_manifest import write_output_manifest
from src.runtime.workflow_orchestrator import WorkflowOrchestrator, WorkflowType


def _write_dummy(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".csv":
        path.write_text("a,b\n1,2\n", encoding="utf-8")
    elif path.suffix == ".md":
        path.write_text("# summary\n", encoding="utf-8")
    else:
        path.write_text("{}", encoding="utf-8")


def _write_contract_outputs(run_mode: str, output_dir: Path, *, include_handoff: bool = False) -> None:
    contract = get_artifact_contract(run_mode)
    artifacts: dict[str, Path] = {}
    for spec in contract.required:
        path = output_dir / spec.filename
        if spec.name != "run_manifest":
            _write_dummy(path)
        artifacts[spec.name] = path

    if include_handoff:
        handoff_spec = next(spec for spec in contract.optional if spec.name == "paper_handoff")
        handoff_path = output_dir / handoff_spec.filename
        _write_dummy(handoff_path)
        artifacts["paper_handoff"] = handoff_path

    write_output_manifest(
        output_dir=output_dir,
        run_mode=contract.run_mode,
        provider_name="indian_csv",
        artifacts=artifacts,
        contract_id=contract.contract_id,
        expected_artifacts=contract.required_names,
        schema_version=contract.schema_version,
        safety_mode=contract.safety_mode,
    )


def _make_fake_executor(tmp_path: Path):
    def _fake_execute(self, command):  # noqa: ANN001
        script_name = Path(command[1]).name
        if script_name == "run_nifty50_zerodha_research.py":
            out_dir = Path(command[command.index("--output-dir") + 1])
            _write_contract_outputs("research", out_dir)
        elif script_name == "run_paper_trading.py":
            out_dir = Path(command[command.index("--paper-output-dir") + 1])
            _write_contract_outputs("paper", out_dir)
        elif script_name == "run_live_signal_pipeline.py":
            out_dir = Path(command[command.index("--output-dir") + 1])
            include_handoff = "--paper-handoff" in command
            _write_contract_outputs("live_safe", out_dir, include_handoff=include_handoff)
        else:
            raise AssertionError(f"Unexpected command: {command}")
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    return _fake_execute


def test_workflow_orchestrator_research_smoke_success(tmp_path: Path, monkeypatch) -> None:
    orchestrator = WorkflowOrchestrator(root_dir=tmp_path)
    monkeypatch.setattr(
        WorkflowOrchestrator,
        "_execute_command",
        _make_fake_executor(tmp_path),
    )

    result = orchestrator.run(
        WorkflowType.RESEARCH_SMOKE,
        output_root=tmp_path / "research",
        symbols_limit=2,
    )

    assert result.success is True
    assert len(result.steps) == 1
    assert result.steps[0].contract_valid is True


def test_workflow_orchestrator_live_to_paper_handoff_requires_handoff_artifact(
    tmp_path: Path,
    monkeypatch,
) -> None:
    orchestrator = WorkflowOrchestrator(root_dir=tmp_path)
    monkeypatch.setattr(
        WorkflowOrchestrator,
        "_execute_command",
        _make_fake_executor(tmp_path),
    )

    result = orchestrator.run(
        WorkflowType.LIVE_SAFE_TO_PAPER_HANDOFF,
        output_root=tmp_path / "handoff",
    )
    assert result.success is True
    assert result.steps[0].contract_valid is True


def test_run_release_smoke_stops_on_failure(tmp_path: Path, monkeypatch) -> None:
    orchestrator = WorkflowOrchestrator(root_dir=tmp_path)
    success_executor = _make_fake_executor(tmp_path)

    def _mixed_execute(self, command):  # noqa: ANN001
        if Path(command[1]).name == "run_paper_trading.py":
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="fail")
        return success_executor(self, command)

    monkeypatch.setattr(WorkflowOrchestrator, "_execute_command", _mixed_execute)
    results = orchestrator.run_release_smoke(output_root=tmp_path / "smoke", symbols_limit=2)

    assert results["research_smoke"].success is True
    assert results["paper_smoke"].success is False
    assert "live_safe_smoke" not in results
