"""
Lightweight workflow orchestration for repeatable runtime smoke paths.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterable

from src.runtime.contract_validation import (
    ArtifactContractValidationError,
    assert_artifact_contract,
)
from src.runtime.run_profiles import RunMode


class WorkflowOrchestratorError(RuntimeError):
    """Raised when workflow orchestration fails."""


class WorkflowType(str, Enum):
    RESEARCH_SMOKE = "research_smoke"
    PAPER_SMOKE = "paper_smoke"
    LIVE_SAFE_SMOKE = "live_safe_smoke"
    RESEARCH_TO_POLICY = "research_to_policy"
    LIVE_SAFE_TO_PAPER_HANDOFF = "live_safe_to_paper_handoff"


@dataclass(frozen=True)
class WorkflowStep:
    name: str
    command: list[str]
    run_mode: RunMode
    output_dir: Path
    required_overrides: tuple[str, ...] = field(default_factory=tuple)


@dataclass
class WorkflowStepResult:
    name: str
    command: list[str]
    return_code: int
    success: bool
    output_dir: str
    contract_valid: bool
    contract_errors: list[str] = field(default_factory=list)
    stdout_tail: str = ""
    stderr_tail: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "command": list(self.command),
            "return_code": self.return_code,
            "success": self.success,
            "output_dir": self.output_dir,
            "contract_valid": self.contract_valid,
            "contract_errors": list(self.contract_errors),
            "stdout_tail": self.stdout_tail,
            "stderr_tail": self.stderr_tail,
        }


@dataclass
class WorkflowRunResult:
    workflow: WorkflowType
    success: bool
    output_root: str
    steps: list[WorkflowStepResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "workflow": self.workflow.value,
            "success": self.success,
            "output_root": self.output_root,
            "steps": [step.to_dict() for step in self.steps],
            "errors": list(self.errors),
        }


@dataclass
class WorkflowOrchestrator:
    root_dir: Path = field(default_factory=lambda: Path.cwd())
    python_executable: str = field(default_factory=lambda: sys.executable)

    def run(
        self,
        workflow: WorkflowType | str,
        *,
        output_root: str | Path,
        symbols_limit: int = 5,
    ) -> WorkflowRunResult:
        workflow_type = workflow if isinstance(workflow, WorkflowType) else WorkflowType(str(workflow))
        root = Path(output_root)
        root.mkdir(parents=True, exist_ok=True)

        steps = self._build_steps(workflow_type, root, symbols_limit=symbols_limit)
        result = WorkflowRunResult(
            workflow=workflow_type,
            success=True,
            output_root=str(root),
        )

        for step in steps:
            step_result = self._run_step(step)
            result.steps.append(step_result)
            if not step_result.success:
                result.success = False
                result.errors.append(
                    f"{step.name} failed (return_code={step_result.return_code})"
                )
                break

        return result

    def run_release_smoke(
        self,
        *,
        output_root: str | Path,
        symbols_limit: int = 3,
    ) -> dict[str, WorkflowRunResult]:
        workflows = (
            WorkflowType.RESEARCH_SMOKE,
            WorkflowType.PAPER_SMOKE,
            WorkflowType.LIVE_SAFE_SMOKE,
        )
        results: dict[str, WorkflowRunResult] = {}
        for workflow in workflows:
            workflow_output = Path(output_root) / workflow.value
            result = self.run(
                workflow,
                output_root=workflow_output,
                symbols_limit=symbols_limit,
            )
            results[workflow.value] = result
            if not result.success:
                break
        return results

    def _run_step(self, step: WorkflowStep) -> WorkflowStepResult:
        completed = self._execute_command(step.command)
        stdout_tail = _tail_text(completed.stdout)
        stderr_tail = _tail_text(completed.stderr)

        success = completed.returncode == 0
        contract_valid = False
        contract_errors: list[str] = []

        if success:
            try:
                assert_artifact_contract(
                    run_mode=step.run_mode,
                    output_dir=step.output_dir,
                    manifest_path=step.output_dir / "run_manifest.json",
                    require_manifest=True,
                    required_overrides=step.required_overrides or None,
                )
                contract_valid = True
            except ArtifactContractValidationError as exc:
                success = False
                contract_errors.append(str(exc))

        return WorkflowStepResult(
            name=step.name,
            command=step.command,
            return_code=completed.returncode,
            success=success,
            output_dir=str(step.output_dir),
            contract_valid=contract_valid,
            contract_errors=contract_errors,
            stdout_tail=stdout_tail,
            stderr_tail=stderr_tail,
        )

    def _execute_command(self, command: Iterable[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            list(command),
            cwd=self.root_dir,
            text=True,
            capture_output=True,
            check=False,
        )

    def _build_steps(
        self,
        workflow: WorkflowType,
        output_root: Path,
        *,
        symbols_limit: int,
    ) -> list[WorkflowStep]:
        if workflow == WorkflowType.RESEARCH_SMOKE:
            out_dir = output_root
            return [
                WorkflowStep(
                    name="research_smoke",
                    run_mode=RunMode.RESEARCH,
                    output_dir=out_dir,
                    command=[
                        self.python_executable,
                        "scripts/run_nifty50_zerodha_research.py",
                        "--symbols-limit",
                        str(symbols_limit),
                        "--output-dir",
                        str(out_dir),
                    ],
                )
            ]

        if workflow == WorkflowType.PAPER_SMOKE:
            out_dir = output_root
            return [
                WorkflowStep(
                    name="paper_smoke",
                    run_mode=RunMode.PAPER,
                    output_dir=out_dir,
                    command=[
                        self.python_executable,
                        "scripts/run_paper_trading.py",
                        "--paper-trading",
                        "--provider",
                        "indian_csv",
                        "--symbols",
                        "RELIANCE.NS",
                        "TCS.NS",
                        "INFY.NS",
                        "--interval",
                        "day",
                        "--paper-output-dir",
                        str(out_dir),
                        "--paper-max-orders",
                        "10",
                    ],
                )
            ]

        if workflow == WorkflowType.LIVE_SAFE_SMOKE:
            out_dir = output_root
            return [
                WorkflowStep(
                    name="live_safe_smoke",
                    run_mode=RunMode.LIVE_SAFE,
                    output_dir=out_dir,
                    command=[
                        self.python_executable,
                        "scripts/run_live_signal_pipeline.py",
                        "--live-signals",
                        "--provider",
                        "indian_csv",
                        "--symbols",
                        "RELIANCE.NS",
                        "TCS.NS",
                        "INFY.NS",
                        "--interval",
                        "day",
                        "--run-once",
                        "--output-dir",
                        str(out_dir),
                    ],
                )
            ]

        if workflow == WorkflowType.RESEARCH_TO_POLICY:
            out_dir = output_root
            return [
                WorkflowStep(
                    name="research_to_policy",
                    run_mode=RunMode.RESEARCH,
                    output_dir=out_dir,
                    command=[
                        self.python_executable,
                        "scripts/run_nifty50_zerodha_research.py",
                        "--symbols-limit",
                        str(symbols_limit),
                        "--regime-analysis",
                        "--build-regime-policy",
                        "--output-dir",
                        str(out_dir),
                    ],
                )
            ]

        if workflow == WorkflowType.LIVE_SAFE_TO_PAPER_HANDOFF:
            out_dir = output_root
            return [
                WorkflowStep(
                    name="live_safe_to_paper_handoff",
                    run_mode=RunMode.LIVE_SAFE,
                    output_dir=out_dir,
                    required_overrides=(
                        "signals",
                        "watchlist",
                        "regime_snapshot",
                        "session_state",
                        "session_summary",
                        "paper_handoff",
                        "run_manifest",
                    ),
                    command=[
                        self.python_executable,
                        "scripts/run_live_signal_pipeline.py",
                        "--live-signals",
                        "--provider",
                        "indian_csv",
                        "--symbols",
                        "RELIANCE.NS",
                        "TCS.NS",
                        "INFY.NS",
                        "--interval",
                        "day",
                        "--run-once",
                        "--paper-handoff",
                        "--output-dir",
                        str(out_dir),
                    ],
                )
            ]

        raise WorkflowOrchestratorError(f"Unsupported workflow: {workflow.value}")


def _tail_text(value: str, max_lines: int = 25) -> str:
    lines = str(value or "").splitlines()
    return "\n".join(lines[-max_lines:])
