"""
Targeted tests for E1: NSE holiday calendar externalized to YAML.

Verifies that:
- Known holiday dates return False for is_trading_day().
- Known trading days return True.
- Missing holiday file raises TradingCalendarError with a helpful message.
- A badly formed YAML raises TradingCalendarError.
- An unknown year (no entries) logs a warning but does not crash.
- The explicit holidays= override still works (backward compat).
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import pytest
import yaml

from src.instruments.calendar import TradingCalendar, TradingCalendarError


# ---------------------------------------------------------------------------
# Fixture: minimal valid YAML holiday file for tests
# ---------------------------------------------------------------------------

SAMPLE_YAML = """\
holidays:
  "2025-01-26": "Republic Day"
  "2025-04-18": "Good Friday"
  "2026-01-26": "Republic Day"
"""


@pytest.fixture()
def holiday_yaml_file(tmp_path):
    """Write a minimal YAML calendar and return its path."""
    p = tmp_path / "nse_holidays.yaml"
    p.write_text(SAMPLE_YAML, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Happy path: load from YAML
# ---------------------------------------------------------------------------

class TestLoadFromYaml:
    def test_known_holiday_is_not_trading_day(self, holiday_yaml_file):
        cal = TradingCalendar(holiday_file=holiday_yaml_file)
        assert not cal.is_trading_day(date(2025, 1, 26)), "Republic Day should not be a trading day"

    def test_known_holiday_good_friday(self, holiday_yaml_file):
        cal = TradingCalendar(holiday_file=holiday_yaml_file)
        assert not cal.is_trading_day(date(2025, 4, 18)), "Good Friday should not be a trading day"

    def test_regular_weekday_is_trading_day(self, holiday_yaml_file):
        # 2025-03-03 is a Monday, no holiday
        cal = TradingCalendar(holiday_file=holiday_yaml_file)
        assert cal.is_trading_day(date(2025, 3, 3))

    def test_weekend_is_not_trading_day(self, holiday_yaml_file):
        cal = TradingCalendar(holiday_file=holiday_yaml_file)
        # 2025-03-01 is a Saturday
        assert not cal.is_trading_day(date(2025, 3, 1))

    def test_2026_holiday_loaded(self, holiday_yaml_file):
        cal = TradingCalendar(holiday_file=holiday_yaml_file)
        assert not cal.is_trading_day(date(2026, 1, 26))


# ---------------------------------------------------------------------------
# Default YAML file (config/nse_holidays.yaml) loads correctly
# ---------------------------------------------------------------------------

class TestDefaultYamlFile:
    """Smoke-test loading from the real project YAML."""

    def test_default_calendar_instantiates(self):
        """TradingCalendar() must succeed when config/nse_holidays.yaml is present."""
        cal = TradingCalendar()
        # Just check it loaded something
        assert len(cal._holidays) > 10

    def test_2026_republic_day_in_default(self):
        cal = TradingCalendar()
        assert not cal.is_trading_day(date(2026, 1, 26))

    def test_2025_christmas_in_default(self):
        cal = TradingCalendar()
        assert not cal.is_trading_day(date(2025, 12, 25))


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

class TestMissingFile:
    def test_missing_yaml_raises_calendar_error(self, tmp_path):
        missing = tmp_path / "does_not_exist.yaml"
        with pytest.raises(TradingCalendarError, match="not found"):
            TradingCalendar(holiday_file=missing)

    def test_error_message_is_helpful(self, tmp_path):
        missing = tmp_path / "nse_holidays.yaml"
        with pytest.raises(TradingCalendarError) as exc_info:
            TradingCalendar(holiday_file=missing)
        assert "nse_holidays.yaml" in str(exc_info.value) or "not found" in str(exc_info.value)


class TestMalformedYaml:
    def test_no_holidays_key_raises(self, tmp_path):
        p = tmp_path / "bad.yaml"
        p.write_text("not_holidays:\n  '2025-01-01': 'Test'\n", encoding="utf-8")
        with pytest.raises(TradingCalendarError, match="top-level 'holidays' key"):
            TradingCalendar(holiday_file=p)

    def test_holidays_is_not_mapping_raises(self, tmp_path):
        p = tmp_path / "bad2.yaml"
        p.write_text("holidays:\n  - '2025-01-01'\n", encoding="utf-8")
        with pytest.raises(TradingCalendarError, match="mapping"):
            TradingCalendar(holiday_file=p)

    def test_invalid_date_string_raises(self, tmp_path):
        p = tmp_path / "bad3.yaml"
        p.write_text("holidays:\n  'not-a-date': 'Test'\n", encoding="utf-8")
        with pytest.raises(TradingCalendarError, match="Invalid date"):
            TradingCalendar(holiday_file=p)


# ---------------------------------------------------------------------------
# Unknown year: no crash, returns True (safe default)
# ---------------------------------------------------------------------------

class TestUnknownYear:
    def test_weekday_in_unlisted_year_defaults_to_trading_day(self, holiday_yaml_file, caplog):
        """A weekday in a year with no YAML entries should be treated as a trading day."""
        cal = TradingCalendar(holiday_file=holiday_yaml_file)
        # 2030-06-03 is a Monday; no 2030 holidays in sample YAML
        with caplog.at_level(logging.DEBUG):
            result = cal.is_trading_day(date(2030, 6, 3))
        assert result is True

    def test_weekend_in_unlisted_year_is_still_not_trading(self, holiday_yaml_file):
        cal = TradingCalendar(holiday_file=holiday_yaml_file)
        # 2030-06-01 is a Saturday
        assert not cal.is_trading_day(date(2030, 6, 1))


# ---------------------------------------------------------------------------
# Backward compat: explicit holidays= tuple still works
# ---------------------------------------------------------------------------

class TestExplicitHolidaysOverride:
    def test_explicit_holidays_bypass_yaml(self):
        """Passing holidays= directly must not try to read any YAML file."""
        cal = TradingCalendar(holidays=(date(2025, 6, 16),))
        assert not cal.is_trading_day(date(2025, 6, 16))
        # A regular weekday not in the explicit set should be a trading day
        assert cal.is_trading_day(date(2025, 6, 17))

    def test_add_holidays_works(self, holiday_yaml_file):
        cal = TradingCalendar(holiday_file=holiday_yaml_file)
        new_holiday = date(2025, 7, 4)
        cal.add_holidays(new_holiday)
        assert not cal.is_trading_day(new_holiday)
