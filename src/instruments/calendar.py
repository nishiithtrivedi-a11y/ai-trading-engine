"""
Trading calendar and expiry model for Indian markets.

This is a stub implementation that provides:
- Weekend-based trading day detection (Mon–Fri)
- NSE monthly expiry convention (last Thursday of the month)
- NSE weekly expiry convention (nearest Thursday)
- Placeholder for holiday calendar integration

The holiday list is empty by default.  Populate ``NSE_HOLIDAYS`` with
actual NSE holiday dates to enable accurate trading-day arithmetic.
Future versions will load holidays from a data file or API.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional


class TradingCalendarError(ValueError):
    """Raised when a calendar operation fails."""


class TradingCalendar:
    """
    Trading calendar for Indian markets.

    Parameters
    ----------
    holidays:
        Optional sequence of non-trading dates in addition to weekends.
        Defaults to the class-level ``NSE_HOLIDAYS`` tuple.
    """

    #: Known NSE holidays.
    NSE_HOLIDAYS: tuple[date, ...] = (
        # 2025 NSE Holidays
        date(2025, 1, 26),   # Republic Day
        date(2025, 2, 26),   # Mahashivratri
        date(2025, 3, 14),   # Holi
        date(2025, 3, 31),   # Id-ul-Fitr (Ramzan Eid) - tentative
        date(2025, 4, 14),   # Dr. Baba Saheb Ambedkar Jayanti
        date(2025, 4, 18),   # Good Friday
        date(2025, 5, 1),    # Maharashtra Day
        date(2025, 8, 15),   # Independence Day
        date(2025, 8, 27),   # Ganesh Chaturthi
        date(2025, 10, 2),   # Mahatma Gandhi Jayanti / Dussehra
        date(2025, 10, 20),  # Diwali Laxmi Pujan (tentative)
        date(2025, 10, 21),  # Diwali Balipratipada
        date(2025, 11, 5),   # Gurunanak Jayanti
        date(2025, 12, 25),  # Christmas
        # 2026 NSE trading holidays (NSE Circular Ref. No. 212/2025, dated 2025-12-12)
        date(2026, 1, 26),   # Republic Day
        date(2026, 3, 3),    # Holi
        date(2026, 3, 26),   # Shri Ram Navami
        date(2026, 3, 31),   # Shri Mahavir Jayanti
        date(2026, 4, 3),    # Good Friday
        date(2026, 4, 14),   # Dr. Baba Saheb Ambedkar Jayanti
        date(2026, 5, 1),    # Maharashtra Day
        date(2026, 5, 28),   # Bakri Id
        date(2026, 6, 26),   # Muharram
        date(2026, 9, 14),   # Ganesh Chaturthi
        date(2026, 10, 2),   # Mahatma Gandhi Jayanti
        date(2026, 10, 20),  # Dussehra
        date(2026, 11, 10),  # Diwali-Balipratipada
        date(2026, 11, 24),  # Prakash Gurpurb Sri Guru Nanak Dev
        date(2026, 12, 25),  # Christmas
    )

    def __init__(
        self,
        holidays: Optional[tuple[date, ...]] = None,
    ) -> None:
        self._holidays: frozenset[date] = frozenset(
            holidays if holidays is not None else self.NSE_HOLIDAYS
        )

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
            f"holidays={len(self._holidays)}, "
            f"nse_holidays={len(self.NSE_HOLIDAYS)})"
        )
