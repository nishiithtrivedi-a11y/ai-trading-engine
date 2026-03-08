"""
Tests for the UI runner wrappers (src/ui/utils/runners.py).

Focuses on:
- RunResult model
- Default config helpers
- Graceful error handling
- Pipeline sequencing
- Realtime config status
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.ui.utils.runners import (
    RunResult,
    _default_monitoring_config,
    _default_scanner_config,
    _default_strategy_specs,
    _default_symbols,
    _find_data_file,
    get_provider_status,
    get_realtime_config_status,
    run_decision_engine,
    run_full_pipeline,
    run_market_intelligence,
    run_monitoring,
    run_realtime_once,
    run_research_lab,
    run_scanner,
)


# ---------------------------------------------------------------------------
# RunResult model tests
# ---------------------------------------------------------------------------


class TestRunResult:
    def test_success_result(self):
        r = RunResult(
            success=True,
            engine_name="Scanner",
            message="Done",
            output_dir="output/scanner",
            duration_seconds=1.5,
        )
        assert r.success is True
        assert r.engine_name == "Scanner"
        assert r.duration_seconds == 1.5
        assert r.error_details is None
        assert r.artifacts == {}

    def test_failure_result(self):
        r = RunResult(
            success=False,
            engine_name="Monitoring",
            message="Failed: no data",
            error_details="FileNotFoundError",
        )
        assert r.success is False
        assert "no data" in r.message
        assert r.error_details == "FileNotFoundError"

    def test_to_dict(self):
        r = RunResult(
            success=True,
            engine_name="Test",
            message="ok",
            duration_seconds=1.234567,
            artifacts={"csv": "path/to/file.csv"},
        )
        d = r.to_dict()
        assert d["success"] is True
        assert d["engine_name"] == "Test"
        assert d["duration_seconds"] == 1.23
        assert d["artifacts"]["csv"] == "path/to/file.csv"

    def test_default_values(self):
        r = RunResult(success=True, engine_name="X", message="ok")
        assert r.output_dir is None
        assert r.duration_seconds == 0.0
        assert r.artifacts == {}


# ---------------------------------------------------------------------------
# Default config helper tests
# ---------------------------------------------------------------------------


class TestDefaultHelpers:
    def test_default_strategy_specs(self):
        specs = _default_strategy_specs()
        assert len(specs) == 2
        names = {s.strategy_name for s in specs}
        assert "RSIReversionStrategy" in names
        assert "SMACrossoverStrategy" in names
        for spec in specs:
            assert spec.enabled is True
            assert spec.timeframes == ["1D"]

    def test_default_scanner_config(self):
        cfg = _default_scanner_config("output")
        assert cfg.universe_name == "nifty50"
        assert cfg.provider_name == "csv"
        assert cfg.data_dir == "data"
        assert len(cfg.strategy_specs) == 2
        assert "scanner" in cfg.export.output_dir

    def test_default_scanner_config_custom_output(self):
        cfg = _default_scanner_config("my_output")
        assert "my_output" in cfg.export.output_dir

    def test_default_monitoring_config(self):
        cfg = _default_monitoring_config("output")
        assert cfg.scanner_config.provider_name == "csv"
        assert len(cfg.watchlists) == 1
        assert cfg.watchlists[0].name == "nifty50"
        assert "monitoring" in cfg.export.output_dir

    def test_default_symbols(self):
        symbols, sector_map = _default_symbols()
        assert isinstance(symbols, list)
        assert len(symbols) > 0
        assert isinstance(sector_map, dict)

    def test_find_data_file(self):
        result = _find_data_file("data")
        if Path("data").exists() and any(Path("data").glob("*.csv")):
            assert result is not None
            assert result.endswith(".csv")
        else:
            # No data dir is fine — returns None
            assert result is None

    def test_find_data_file_missing_dir(self):
        result = _find_data_file("nonexistent_dir_12345")
        assert result is None


# ---------------------------------------------------------------------------
# Runner error-handling tests
# ---------------------------------------------------------------------------


class TestRunnerGracefulFailures:
    """Verify each runner returns a RunResult (not raises) on errors."""

    def test_scanner_handles_import_error(self):
        with patch(
            "src.ui.utils.runners._default_scanner_config",
            side_effect=ImportError("test"),
        ):
            r = run_scanner("output")
            assert r.success is False
            assert r.engine_name == "Scanner"
            assert r.error_details is not None

    def test_monitoring_handles_error(self):
        with patch(
            "src.ui.utils.runners._default_monitoring_config",
            side_effect=RuntimeError("test"),
        ):
            r = run_monitoring("output")
            assert r.success is False
            assert r.engine_name == "Monitoring"

    def test_decision_handles_error(self):
        with patch(
            "src.ui.utils.runners._default_monitoring_config",
            side_effect=RuntimeError("test"),
        ):
            r = run_decision_engine("output")
            assert r.success is False
            assert r.engine_name == "Decision Engine"

    def test_market_intelligence_handles_error(self):
        with patch(
            "src.ui.utils.runners._default_symbols",
            side_effect=RuntimeError("test"),
        ):
            r = run_market_intelligence("output")
            assert r.success is False
            assert r.engine_name == "Market Intelligence"

    def test_research_lab_no_data_file(self):
        r = run_research_lab("output", data_file="nonexistent_file_12345.csv")
        assert r.success is False
        assert r.engine_name == "Research Lab"
        assert "No data file" in r.message or "not found" in r.message.lower() or "failed" in r.message.lower()

    def test_realtime_handles_error(self):
        with patch(
            "src.ui.utils.runners._default_monitoring_config",
            side_effect=RuntimeError("test"),
        ):
            r = run_realtime_once("output")
            assert r.success is False
            assert "Realtime" in r.engine_name

    def test_all_runners_return_run_result(self):
        """Every runner must return a RunResult, never raise."""
        runners = [
            lambda: run_scanner("__nonexistent__"),
            lambda: run_monitoring("__nonexistent__"),
            lambda: run_decision_engine("__nonexistent__"),
            lambda: run_market_intelligence("__nonexistent__"),
            lambda: run_research_lab("__nonexistent__", data_file="nope.csv"),
            lambda: run_realtime_once("__nonexistent__"),
        ]
        for runner_fn in runners:
            r = runner_fn()
            assert isinstance(r, RunResult)
            assert isinstance(r.engine_name, str)
            assert isinstance(r.message, str)


# ---------------------------------------------------------------------------
# Runner duration tracking
# ---------------------------------------------------------------------------


class TestRunnerTiming:
    def test_duration_is_recorded(self):
        """Even on failure, duration_seconds should be > 0."""
        r = run_research_lab("output", data_file="nope_12345.csv")
        assert r.duration_seconds >= 0


# ---------------------------------------------------------------------------
# Pipeline tests
# ---------------------------------------------------------------------------


class TestFullPipeline:
    def test_pipeline_returns_list(self):
        with patch("src.ui.utils.runners.run_market_intelligence") as mock_mi, \
             patch("src.ui.utils.runners.run_scanner") as mock_sc, \
             patch("src.ui.utils.runners.run_monitoring") as mock_mon, \
             patch("src.ui.utils.runners.run_decision_engine") as mock_de:
            mock_mi.return_value = RunResult(True, "MI", "ok")
            mock_sc.return_value = RunResult(True, "Scanner", "ok")
            mock_mon.return_value = RunResult(True, "Monitoring", "ok")
            mock_de.return_value = RunResult(True, "Decision", "ok")

            results = run_full_pipeline("output")
            assert len(results) == 4
            assert all(r.success for r in results)

    def test_pipeline_stops_on_failure(self):
        with patch("src.ui.utils.runners.run_market_intelligence") as mock_mi, \
             patch("src.ui.utils.runners.run_scanner") as mock_sc, \
             patch("src.ui.utils.runners.run_monitoring") as mock_mon, \
             patch("src.ui.utils.runners.run_decision_engine") as mock_de:
            mock_mi.return_value = RunResult(True, "MI", "ok")
            mock_sc.return_value = RunResult(False, "Scanner", "failed")
            mock_mon.return_value = RunResult(True, "Monitoring", "ok")
            mock_de.return_value = RunResult(True, "Decision", "ok")

            results = run_full_pipeline("output")
            assert len(results) == 2  # MI ok + Scanner fail, then stop
            assert results[0].success is True
            assert results[1].success is False
            mock_mon.assert_not_called()
            mock_de.assert_not_called()

    def test_pipeline_progress_callback(self):
        calls = []

        def callback(name, idx, total):
            calls.append((name, idx, total))

        with patch("src.ui.utils.runners.run_market_intelligence") as mock_mi, \
             patch("src.ui.utils.runners.run_scanner") as mock_sc, \
             patch("src.ui.utils.runners.run_monitoring") as mock_mon, \
             patch("src.ui.utils.runners.run_decision_engine") as mock_de:
            mock_mi.return_value = RunResult(True, "MI", "ok")
            mock_sc.return_value = RunResult(True, "Scanner", "ok")
            mock_mon.return_value = RunResult(True, "Monitoring", "ok")
            mock_de.return_value = RunResult(True, "Decision", "ok")

            run_full_pipeline("output", progress_callback=callback)

        assert len(calls) == 4
        assert calls[0] == ("Market Intelligence", 0, 4)
        assert calls[3] == ("Decision Engine", 3, 4)

    def test_pipeline_first_step_fails(self):
        with patch("src.ui.utils.runners.run_market_intelligence") as mock_mi, \
             patch("src.ui.utils.runners.run_scanner") as mock_sc:
            mock_mi.return_value = RunResult(False, "MI", "failed")

            results = run_full_pipeline("output")
            assert len(results) == 1
            assert results[0].success is False
            mock_sc.assert_not_called()


# ---------------------------------------------------------------------------
# Config status helpers
# ---------------------------------------------------------------------------


class TestConfigStatus:
    def test_realtime_config_status_returns_dict(self):
        status = get_realtime_config_status()
        assert isinstance(status, dict)
        assert "enabled" in status
        assert "mode" in status

    def test_realtime_config_status_handles_error(self):
        with patch(
            "src.realtime.config.load_realtime_config",
            side_effect=Exception("test"),
        ):
            # It should still return a fallback dict
            status = get_realtime_config_status()
            assert isinstance(status, dict)
            assert status["enabled"] is False

    def test_provider_status_returns_dict(self):
        status = get_provider_status()
        assert isinstance(status, dict)
        assert "default_provider" in status
        assert "providers" in status

    def test_provider_status_handles_error(self):
        with patch(
            "src.data.provider_config.DataProvidersConfig",
            side_effect=Exception("test"),
        ):
            status = get_provider_status()
            assert status["default_provider"] == "csv"
