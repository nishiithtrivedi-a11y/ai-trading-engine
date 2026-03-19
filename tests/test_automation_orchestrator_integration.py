"""Targeted integration test for WorkflowOrchestrator signature compatibility."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from src.automation.models import PipelineType
from src.automation.scheduler_service import _orchestrator_runner
from src.runtime.workflow_orchestrator import WorkflowOrchestrator


def test_orchestrator_constructor_compatibility() -> None:
    """
    Verify that WorkflowOrchestrator can be initialized without arguments,
    as expected by the current scheduler_service implementation.
    """
    # This should not raise "unexpected keyword argument"
    orchestrator = WorkflowOrchestrator()
    assert isinstance(orchestrator, WorkflowOrchestrator)


def test_orchestrator_runner_wiring(tmp_path: Path) -> None:
    """
    Verify that _orchestrator_runner correctly initializes and calls the orchestrator.
    """
    output_dir = tmp_path / "runs" / "test_run"
    output_dir.mkdir(parents=True)

    # We mock the .run method to avoid actually executing subprocesses,
    # but we want to ensure the constructor and method call signature match.
    with patch("src.automation.scheduler_service.WorkflowOrchestrator") as MockOrchestrator:
        mock_instance = MockOrchestrator.return_value
        mock_instance.run.return_value = MagicMock(
            success=True,
            errors=[],
            steps=[]
        )

        result = _orchestrator_runner(PipelineType.MORNING_SCAN, str(output_dir))

        # Check constructor call (should have no arguments now)
        MockOrchestrator.assert_called_once_with()
        
        # Check .run() call (should have workflow, output_root, symbols_limit)
        mock_instance.run.assert_called_once()
        args, kwargs = mock_instance.run.call_args
        assert kwargs["workflow"] == PipelineType.MORNING_SCAN
        assert kwargs["output_root"] == str(output_dir)
        assert result["success"] is True
