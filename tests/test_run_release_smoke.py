from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts import run_release_smoke
from src.runtime.workflow_orchestrator import WorkflowRunResult, WorkflowType


def _result(workflow: WorkflowType, success: bool, output_root: Path) -> WorkflowRunResult:
    return WorkflowRunResult(
        workflow=workflow,
        success=success,
        output_root=str(output_root),
        steps=[],
        errors=[] if success else ["failed"],
    )


def test_release_smoke_script_writes_summary_and_returns_success(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def _fake_release_smoke(self, *, output_root, symbols_limit):  # noqa: ANN001
        out = Path(output_root)
        return {
            "research_smoke": _result(WorkflowType.RESEARCH_SMOKE, True, out),
            "paper_smoke": _result(WorkflowType.PAPER_SMOKE, True, out),
            "live_safe_smoke": _result(WorkflowType.LIVE_SAFE_SMOKE, True, out),
        }

    monkeypatch.setattr(
        run_release_smoke.WorkflowOrchestrator,
        "run_release_smoke",
        _fake_release_smoke,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["runner", "--output-dir", str(tmp_path), "--symbols-limit", "2"],
    )

    exit_code = run_release_smoke.main()
    assert exit_code == 0

    summary = tmp_path / "release_smoke_summary.json"
    assert summary.exists()
    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert payload["research_smoke"]["success"] is True


def test_release_smoke_script_returns_failure_if_any_workflow_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def _fake_release_smoke(self, *, output_root, symbols_limit):  # noqa: ANN001
        out = Path(output_root)
        return {
            "research_smoke": _result(WorkflowType.RESEARCH_SMOKE, True, out),
            "paper_smoke": _result(WorkflowType.PAPER_SMOKE, False, out),
        }

    monkeypatch.setattr(
        run_release_smoke.WorkflowOrchestrator,
        "run_release_smoke",
        _fake_release_smoke,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["runner", "--output-dir", str(tmp_path)],
    )

    exit_code = run_release_smoke.main()
    assert exit_code == 1
