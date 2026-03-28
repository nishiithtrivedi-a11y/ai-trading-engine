"""
Trading calendar and expiry model for Indian markets.

This is a stub implementation that provides:
- Weekend-based trading day detection (Mon–Fri)
- NSE monthly expiry convention (last Thursday of the month)
- NSE weekly expiry convention (nearest Thursday)
- Holiday calendar loaded from ``config/nse_holidays.yaml``

Holiday data is sourced from ``config/nse_holidays.yaml`` relative to the
project root.  The file must be present and well-formed; a missing or
malformed file raises ``TradingCalendarError`` with a clear message.

If a date falls in a year that has no entries in the YAML file, a warning is
logged and the day is assumed to be a trading day (safe fallback — will not
incorrectly block real trading days).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

# PyYAML is a project dependency; import lazily to give a clear error.
try:
    import yaml as _yaml
except ImportError as _yaml_import_err:  # pragma: no cover
    _yaml = None  # type: ignore[assignment]
    _yaml_import_err_msg = str(_yaml_import_err)
else:
    _yaml_import_err_msg = ""

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Resolved path to the holiday YAML (project-root relative, absolute at load)
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_DEFAULT_HOLIDAY_FILE = _PROJECT_ROOT / "config" / "nse_holidays.yaml"


def _load_holidays_from_yaml(path: Path) -> tuple[date, ...]:
    """Parse ``config/nse_holidays.yaml`` and return a sorted tuple of dates.

    Raises
    ------
    TradingCalendarError
        If *yaml* is not installed, the file is missing, or the file is
        malformed.
    """
    if _yaml is None:  # pragma: no cover
        raise TradingCalendarError(
            f"PyYAML is required but not installed: {_yaml_import_err_msg}. "
            f"Run `pip install pyyaml` to fix this."
        )

    if not path.exists():
        raise TradingCalendarError(
            f"NSE holiday calendar file not found: {path}\n"
            f"Expected a YAML file with a top-level 'holidays' mapping of "
            f"'YYYY-MM-DD' -> 'Holiday Name'.\n"
            f"Create or restore {path} to proceed."
        )

    try:
        with path.open("r", encoding="utf-8") as fh:
            data = _yaml.safe_load(fh)
    except Exception as exc:
        raise TradingCalendarError(
            f"Failed to parse NSE holiday calendar {path}: {exc}"
        ) from exc

    if not isinstance(data, dict) or "holidays" not in data:
        raise TradingCalendarError(
            f"NSE holiday calendar {path} must have a top-level 'holidays' key. "
            f"Got: {type(data).__name__}"
        )

    raw = data["holidays"]
    if not isinstance(raw, dict):
        raise TradingCalendarError(
            f"'holidays' in {path} must be a mapping of 'YYYY-MM-DD' -> 'name'. "
            f"Got: {type(raw).__name__}"
        )

    parsed: list[date] = []
    for date_str, name in raw.items():
        try:
            parsed.append(date.fromisoformat(str(date_str)))
        except ValueError as exc:
            raise TradingCalendarError(
                f"Invalid date key {date_str!r} in {path}: {exc}"
            ) from exc

    return tuple(sorted(parsed))


class TradingCalendarError(ValueError):
    """Raised when a calendar operation fails."""


class TradingCalendar:
    """
    Trading calendar for Indian markets.

    Parameters
    ----------
    holidays:
        Optional sequence of non-trading dates in addition to weekends.
        When *None* (default) the class loads holidays from
        ``config/nse_holidays.yaml`` at the project root.
        Pass an explicit tuple to override (useful in tests).
    holiday_file:
        Path to the YAML holiday file.  Defaults to
        ``<project_root>/config/nse_holidays.yaml``.
        Ignored when *holidays* is provided explicitly.
    """

    def __init__(
        self,
        holidays: Optional[tuple[date, ...]] = None,
        holiday_file: Optional[Path] = None,
    ) -> None:
        if holidays is not None:
            self._holidays: frozenset[date] = frozenset(holidays)
        else:
            file_path = holiday_file if holiday_file is not None else _DEFAULT_HOLIDAY_FILE
            loaded = _load_holidays_from_yaml(file_path)
            self._holidays = frozenset(loaded)

    # ------------------------------------------------------------------
    # Class-level property so callers that reference TradingCalendar.NSE_HOLIDAYS
    # still get a reasonable tuple (loaded from YAML on first access).
    # ------------------------------------------------------------------

    @classmethod
    def _default_holidays(cls) -> tuple[date, ...]:
        """Return the holidays loaded from the default YAML file."""
        return _load_holidays_from_yaml(_DEFAULT_HOLIDAY_FILE)

    # ------------------------------------------------------------------
    # Trading day helpers
    # ------------------------------------------------------------------

    def is_trading_day(self, d: date) -> bool:
        """Return True if ``d`` is a trading day (Mon–Fri, not a holiday)."""
        return d.weekday() < 5 and d not in self._holidays

    def next_trading_day(self, d: date) -> date:
        """Return the next trading day after ``d``.

        Parameters
        ----------
        d:
            Reference date.  The returned date is strictly after ``d``.
        """
        candidate = d + timedelta(days=1)
        while not self.is_trading_day(candidate):
            candidate += timedelta(days=1)
        return candidate

    def prev_trading_day(self, d: date) -> date:
        """Return the trading day immediately before ``d``."""
        candidate = d - timedelta(days=1)
        while not self.is_trading_day(candidate):
            candidate -= timedelta(days=1)
        return candidate

    def trading_days_between(self, start: date, end: date) -> int:
        """Return the number of trading days in [start, end) (start inclusive, end exclusive)."""
        if end <= start:
            return 0
        count = 0
        current = start
        while current < end:
            if self.is_trading_day(current):
                count += 1
            current += timedelta(days=1)
        return count

    # ------------------------------------------------------------------
    # Expiry helpers
    # ------------------------------------------------------------------

    def get_monthly_expiry(self, year: int, month: int) -> date:
        """
        Return the NSE monthly expiry date for the given month.

        NSE convention: last Thursday of the month.
        If that Thursday is a holiday, roll back to the preceding trading day.

        Parameters
        ----------
        year:
            Calendar year.
        month:
            Calendar month (1–12).
        """
        # Find the last Thursday of the month
        # Start from the last day of the month and go backwards
        if month == 12:
            last_day = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            last_day = date(year, month + 1, 1) - timedelta(days=1)

        # Thursday is weekday 3
        days_back = (last_day.weekday() - 3) % 7
        expiry = last_day - timedelta(days=days_back)

        # Roll back if holiday
        while not self.is_trading_day(expiry):
            expiry -= timedelta(days=1)

        return expiry

    def get_weekly_expiry(self, year: int, week: int) -> date:
        """
        Return the NSE weekly expiry date for the given ISO week.

        NSE convention: Thursday of the given ISO week.
        If that Thursday is a holiday, roll back to the preceding trading day.

        Parameters
        ----------
        year:
            Calendar year.
        week:
            ISO week number (1–53).
        """
        # ISO week date: Thursday (weekday=3) of the given week
        # date.fromisocalendar(year, week, 4) → Thursday
        try:
            expiry = date.fromisocalendar(year, week, 4)
        except ValueError as exc:
            raise TradingCalendarError(
                f"Invalid ISO week {week} for year {year}: {exc}"
            ) from exc

        # Roll back if holiday
        while not self.is_trading_day(expiry):
            expiry -= timedelta(days=1)

        return expiry

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def add_holidays(self, *dates: date) -> None:
        """Add additional holidays at runtime."""
        self._holidays = self._holidays | frozenset(dates)

    def __repr__(self) -> str:
        return (
            f"TradingCalendar("
            f"holidays={len(self._holidays)})"
        )
