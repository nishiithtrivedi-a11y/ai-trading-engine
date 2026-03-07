"""Tests for UI dashboard loader utilities."""

import json

import pandas as pd
import pytest

from src.ui.utils.loaders import (
    load_csv,
    load_json,
    list_output_subdirs,
    find_latest_dir,
    find_file_in_dirs,
    get_data_availability,
    list_backtest_runs,
    load_scanner_opportunities,
    load_monitoring_alerts,
    load_decision_picks,
    load_realtime_status,
    load_strategy_scores,
    load_market_state,
)


class TestLoadCsv:

    def test_load_existing_csv(self, tmp_path):
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("a,b\n1,2\n3,4\n")
        df, err = load_csv(csv_file)
        assert err is None
        assert df is not None
        assert len(df) == 2
        assert list(df.columns) == ["a", "b"]

    def test_load_missing_csv(self, tmp_path):
        df, err = load_csv(tmp_path / "nonexistent.csv")
        assert df is None
        assert "not found" in err.lower()

    def test_load_empty_csv(self, tmp_path):
        csv_file = tmp_path / "empty.csv"
        csv_file.write_text("a,b\n")
        df, err = load_csv(csv_file)
        assert df is None
        assert "empty" in err.lower()


class TestLoadJson:

    def test_load_existing_json(self, tmp_path):
        json_file = tmp_path / "test.json"
        json_file.write_text(json.dumps({"key": "value"}))
        data, err = load_json(json_file)
        assert err is None
        assert data == {"key": "value"}

    def test_load_missing_json(self, tmp_path):
        data, err = load_json(tmp_path / "nonexistent.json")
        assert data is None
        assert "not found" in err.lower()

    def test_load_invalid_json(self, tmp_path):
        json_file = tmp_path / "bad.json"
        json_file.write_text("not valid json{{{")
        data, err = load_json(json_file)
        assert data is None
        assert "error" in err.lower()


class TestDirectoryDiscovery:

    def test_list_output_subdirs(self, tmp_path):
        (tmp_path / "scanner_20260101").mkdir()
        (tmp_path / "monitoring_20260101").mkdir()
        (tmp_path / "file.txt").write_text("not a dir")
        result = list_output_subdirs(str(tmp_path))
        assert "scanner_20260101" in result
        assert "monitoring_20260101" in result
        assert "file.txt" not in result

    def test_list_output_subdirs_missing_dir(self):
        result = list_output_subdirs("/nonexistent/path")
        assert result == []

    def test_find_latest_dir(self, tmp_path):
        d1 = tmp_path / "scanner_old"
        d1.mkdir()
        d2 = tmp_path / "scanner_new"
        d2.mkdir()
        # Touch d2 to make it newer
        (d2 / "marker").write_text("new")
        result = find_latest_dir("scanner", str(tmp_path))
        assert result is not None
        assert result.name == "scanner_new"

    def test_find_latest_dir_no_match(self, tmp_path):
        (tmp_path / "monitoring_x").mkdir()
        result = find_latest_dir("scanner", str(tmp_path))
        assert result is None

    def test_find_file_in_dirs(self, tmp_path):
        d = tmp_path / "scanner_run1"
        d.mkdir()
        (d / "opportunities.csv").write_text("a,b\n1,2\n")
        result = find_file_in_dirs("opportunities.csv", ["scanner"], str(tmp_path))
        assert result is not None
        assert result.name == "opportunities.csv"


class TestPhaseLoaders:

    def test_scanner_missing(self, tmp_path):
        df, err = load_scanner_opportunities(str(tmp_path))
        assert df is None
        assert "scanner" in err.lower()

    def test_scanner_with_data(self, tmp_path):
        d = tmp_path / "scanner_run1"
        d.mkdir()
        (d / "opportunities.csv").write_text("symbol,score\nRELIANCE,80\n")
        df, err = load_scanner_opportunities(str(tmp_path))
        assert err is None
        assert len(df) == 1

    def test_monitoring_alerts_missing(self, tmp_path):
        df, err = load_monitoring_alerts(str(tmp_path))
        assert df is None

    def test_decision_picks_missing(self, tmp_path):
        df, err = load_decision_picks("swing", str(tmp_path))
        assert df is None
        assert "swing" in err.lower()

    def test_realtime_status_missing(self, tmp_path):
        data, err = load_realtime_status(str(tmp_path))
        assert data is None

    def test_strategy_scores_missing(self, tmp_path):
        df, err = load_strategy_scores(str(tmp_path))
        assert df is None

    def test_market_state_missing(self, tmp_path):
        data, err = load_market_state(str(tmp_path))
        assert data is None


class TestDataAvailability:

    def test_all_missing(self, tmp_path):
        avail = get_data_availability(str(tmp_path))
        assert all(v is False for v in avail.values())

    def test_some_available(self, tmp_path):
        (tmp_path / "scanner_run1").mkdir()
        (tmp_path / "realtime").mkdir()
        (tmp_path / "sma_crossover").mkdir()  # backtest dir
        avail = get_data_availability(str(tmp_path))
        assert avail["scanner"] is True
        assert avail["realtime"] is True
        assert avail["backtests"] is True
        assert avail["monitoring"] is False


class TestListBacktestRuns:

    def test_filters_non_backtest_dirs(self, tmp_path):
        (tmp_path / "sma_crossover").mkdir()
        (tmp_path / "rsi_reversion").mkdir()
        (tmp_path / "scanner_run1").mkdir()
        (tmp_path / "monitoring_run1").mkdir()
        (tmp_path / "decision_run1").mkdir()
        runs = list_backtest_runs(str(tmp_path))
        assert "sma_crossover" in runs
        assert "rsi_reversion" in runs
        assert "scanner_run1" not in runs
        assert "monitoring_run1" not in runs
        assert "decision_run1" not in runs
