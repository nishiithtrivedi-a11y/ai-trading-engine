"""Tests for UI dashboard formatter utilities."""

import pandas as pd
import pytest

from src.ui.utils.formatters import (
    fmt_pct,
    fmt_pct_already,
    fmt_currency,
    fmt_number,
    fmt_ratio,
    fmt_signal,
    fmt_horizon,
    fmt_timestamp,
    fmt_date,
    fmt_bool,
    color_pnl,
    color_score,
    metrics_to_display_dict,
    clean_column_name,
    style_dataframe,
)


class TestFmtPct:

    def test_positive(self):
        assert fmt_pct(0.1234) == "12.34%"

    def test_negative(self):
        assert fmt_pct(-0.05) == "-5.00%"

    def test_zero(self):
        assert fmt_pct(0) == "0.00%"

    def test_none(self):
        assert fmt_pct(None) == "N/A"

    def test_custom_decimals(self):
        assert fmt_pct(0.12345, decimals=1) == "12.3%"


class TestFmtPctAlready:

    def test_basic(self):
        assert fmt_pct_already(12.34) == "12.34%"

    def test_none(self):
        assert fmt_pct_already(None) == "N/A"


class TestFmtCurrency:

    def test_basic(self):
        assert fmt_currency(100000) == "100,000"

    def test_with_symbol(self):
        assert fmt_currency(1500.5, symbol="$", decimals=2) == "$1,500.50"

    def test_none(self):
        assert fmt_currency(None) == "N/A"


class TestFmtNumber:

    def test_float(self):
        assert fmt_number(1234.567) == "1,234.57"

    def test_integer(self):
        assert fmt_number(42, decimals=0) == "42"

    def test_none(self):
        assert fmt_number(None) == "N/A"


class TestFmtRatio:

    def test_basic(self):
        assert fmt_ratio(1.234) == "1.23"

    def test_none(self):
        assert fmt_ratio(None) == "N/A"


class TestFmtSignal:

    def test_buy(self):
        assert fmt_signal("buy") == "BUY"

    def test_none(self):
        assert fmt_signal(None) == "-"


class TestFmtHorizon:

    def test_basic(self):
        assert fmt_horizon("intraday") == "Intraday"

    def test_snake_case(self):
        assert fmt_horizon("high_priority") == "High Priority"

    def test_none(self):
        assert fmt_horizon(None) == "-"


class TestFmtTimestamp:

    def test_iso_string(self):
        result = fmt_timestamp("2024-01-15T10:30:00")
        assert "2024-01-15" in result

    def test_none(self):
        assert fmt_timestamp(None) == "N/A"


class TestFmtDate:

    def test_basic(self):
        result = fmt_date("2024-01-15T10:30:00")
        assert result == "2024-01-15"

    def test_none(self):
        assert fmt_date(None) == "N/A"


class TestFmtBool:

    def test_true(self):
        assert fmt_bool(True) == "Yes"

    def test_false(self):
        assert fmt_bool(False) == "No"

    def test_none(self):
        assert fmt_bool(None) == "N/A"


class TestColorPnl:

    def test_positive(self):
        assert color_pnl(100) == "green"

    def test_negative(self):
        assert color_pnl(-50) == "red"

    def test_zero(self):
        assert color_pnl(0) == "gray"

    def test_none(self):
        assert color_pnl(None) == "gray"


class TestColorScore:

    def test_low(self):
        assert color_score(20) == "red"

    def test_medium(self):
        assert color_score(50) == "orange"

    def test_high(self):
        assert color_score(70) == "blue"

    def test_excellent(self):
        assert color_score(90) == "green"

    def test_none(self):
        assert color_score(None) == "gray"


class TestMetricsToDisplayDict:

    def test_formats_known_keys(self):
        metrics = {
            "sharpe_ratio": 1.5,
            "max_drawdown_pct": 0.12,
            "num_trades": 25,
            "final_value": 115000,
        }
        result = metrics_to_display_dict(metrics)
        assert result["sharpe_ratio"] == "1.50"
        assert "12.00%" in result["max_drawdown_pct"]
        assert "25" in result["num_trades"]

    def test_filters_by_keys(self):
        metrics = {"sharpe_ratio": 1.5, "sortino_ratio": 2.0, "extra": 99}
        result = metrics_to_display_dict(metrics, keys=["sharpe_ratio"])
        assert "sharpe_ratio" in result
        assert "sortino_ratio" not in result
        assert "extra" not in result


class TestCleanColumnName:

    def test_basic(self):
        assert clean_column_name("total_return_pct") == "Total Return Pct"

    def test_single(self):
        assert clean_column_name("symbol") == "Symbol"


class TestStyleDataframe:

    def test_renames_columns(self):
        df = pd.DataFrame({"total_return_pct": [0.1], "num_trades": [5]})
        styled = style_dataframe(df)
        assert "Total Return Pct" in styled.columns
        assert "Num Trades" in styled.columns
