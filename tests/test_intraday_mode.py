"""
Intraday mode regression tests.

Covers:
- Holding minutes computation on Position
- UTC timestamp → IST session-boundary detection (_is_last_bar_of_session)
- Force square-off fires at correct bar for UTC-stamped 5M data
- No overnight carry when force_square_off_at_close=True
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from src.core.data_handler import DataHandler
from src.core.backtest_engine import BacktestEngine
from src.core.position import Position, PositionSide
from src.strategies.sma_crossover import SMACrossoverStrategy
from src.utils.config import BacktestConfig, PositionSizingMethod, RiskConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_intraday_5m_utc(num_days: int = 3) -> DataHandler:
    """Build synthetic 5-minute OHLCV data with UTC timestamps, like RELIANCE_5M.csv.

    Each day has bars 03:45–09:55 UTC (= 09:15–15:25 IST), matching real NSE data.
    """
    bars = []
    base_price = 1500.0
    bar_num = 0

    trading_dates = pd.bdate_range("2025-12-10", periods=num_days, freq="B")

    for day in trading_dates:
        # 09:15–15:25 IST = 03:45–09:55 UTC
        session_start_utc = day.replace(hour=3, minute=45, tzinfo=None)
        session = pd.date_range(
            start=session_start_utc.tz_localize("UTC"),
            periods=75,
            freq="5min",
        )
        for ts in session:
            p = base_price + bar_num * 0.1
            bars.append({
                "timestamp": ts,
                "open": p,
                "high": p + 1,
                "low": p - 1,
                "close": p,
                "volume": 100_000,
            })
            bar_num += 1

    df = pd.DataFrame(bars).set_index("timestamp")
    return DataHandler(df)


def _make_intraday_config(tmp_path) -> BacktestConfig:
    return BacktestConfig(
        initial_capital=100_000,
        fee_rate=0.001,
        slippage_rate=0.0,
        position_sizing=PositionSizingMethod.PERCENT_OF_EQUITY,
        position_size_pct=0.95,
        intraday=True,
        force_square_off_at_close=True,
        allow_entries_only_during_market_hours=True,
        market_timezone="Asia/Kolkata",
        risk=RiskConfig(stop_loss_pct=None, trailing_stop_pct=None),
        strategy_params={"fast_period": 5, "slow_period": 10},
        output_dir=str(tmp_path / "intraday"),
        data_file="data/sample_data.csv",
    )


# ---------------------------------------------------------------------------
# Original test (preserved)
# ---------------------------------------------------------------------------

def test_holding_minutes():
    pos = Position(
        side=PositionSide.LONG,
        entry_price=100.0,
        quantity=10,
        entry_timestamp=pd.Timestamp("2025-01-15 09:15:00"),
        entry_bar_index=0,
    )
    minutes = pos.holding_minutes(pd.Timestamp("2025-01-15 10:00:00"))
    assert minutes == 45.0


# ---------------------------------------------------------------------------
# UTC → IST session-boundary detection
# ---------------------------------------------------------------------------

class TestIsLastBarOfSession:

    def _make_engine(self, tmp_path, num_days=3):
        dh = _make_intraday_5m_utc(num_days)
        config = _make_intraday_config(tmp_path)
        engine = BacktestEngine(config, SMACrossoverStrategy())
        engine.data_handler = dh
        return engine, dh

    def test_last_utc_bar_of_day_is_detected(self, tmp_path):
        """Bar at 09:55 UTC (15:25 IST) should be last bar of session when next bar is next day."""
        engine, dh = self._make_engine(tmp_path)
        # Index 74 = last bar of day 0 (09:55 UTC = 15:25 IST)
        last_bar_idx = 74
        ts = dh.data.index[last_bar_idx]
        assert engine._is_last_bar_of_session(ts, last_bar_idx) is True

    def test_first_bar_of_day_is_not_last(self, tmp_path):
        """Bar at 03:45 UTC (09:15 IST) is NOT the last bar of its session."""
        engine, dh = self._make_engine(tmp_path)
        ts = dh.data.index[0]  # first bar of first day
        assert engine._is_last_bar_of_session(ts, 0) is False

    def test_mid_session_bar_is_not_last(self, tmp_path):
        """A bar in the middle of a session is not the last bar."""
        engine, dh = self._make_engine(tmp_path)
        ts = dh.data.index[37]  # mid-session bar
        assert engine._is_last_bar_of_session(ts, 37) is False

    def test_absolute_last_bar_is_detected(self, tmp_path):
        """The very last bar in the dataset is always the session end."""
        engine, dh = self._make_engine(tmp_path)
        last_idx = len(dh) - 1
        ts = dh.data.index[last_idx]
        assert engine._is_last_bar_of_session(ts, last_idx) is True

    def test_second_day_last_bar_detected(self, tmp_path):
        """Last bar of day 1 (bar index 149) should also be detected."""
        engine, dh = self._make_engine(tmp_path, num_days=3)
        idx = 149  # last bar of day 1
        ts = dh.data.index[idx]
        assert engine._is_last_bar_of_session(ts, idx) is True

    def test_second_day_first_bar_not_last(self, tmp_path):
        """First bar of day 1 (bar index 75) should NOT be detected as session end."""
        engine, dh = self._make_engine(tmp_path, num_days=3)
        idx = 75  # first bar of day 1
        ts = dh.data.index[idx]
        assert engine._is_last_bar_of_session(ts, idx) is False


# ---------------------------------------------------------------------------
# Full backtest: no overnight carry with force_square_off_at_close=True
# ---------------------------------------------------------------------------

class TestNoOvernightCarry:

    def test_no_trade_exceeds_one_session(self, tmp_path):
        """All trades must close within a single session when force_square_off=True."""
        import warnings
        import logging
        warnings.filterwarnings("ignore")
        logging.disable(logging.CRITICAL)

        dh = _make_intraday_5m_utc(num_days=5)
        config = _make_intraday_config(tmp_path)
        strategy = SMACrossoverStrategy()

        engine = BacktestEngine(config, strategy)
        engine.run(dh)
        results = engine.get_results()
        trade_log = results["trade_log"]

        if trade_log.empty:
            return  # no trades generated → constraint trivially satisfied

        # NSE session = 75 × 5min bars = 375 minutes.
        # Allow a 5-minute tolerance for same-bar close execution.
        max_allowed_minutes = 375
        assert trade_log["holding_minutes"].max() <= max_allowed_minutes, (
            f"Overnight carry detected: longest trade = "
            f"{trade_log['holding_minutes'].max():.0f} min"
        )

    def test_force_square_off_disabled_allows_overnight(self, tmp_path):
        """Sanity check: disabling force_square_off can produce multi-session holds."""
        import warnings
        import logging
        warnings.filterwarnings("ignore")
        logging.disable(logging.CRITICAL)

        dh = _make_intraday_5m_utc(num_days=5)
        config = _make_intraday_config(tmp_path)
        config = config.model_copy(
            update={"force_square_off_at_close": False, "intraday": False}
        )
        strategy = SMACrossoverStrategy()
        engine = BacktestEngine(config, strategy)
        engine.run(dh)
        # This test just verifies the engine runs without error; we don't
        # assert on holding_minutes because daily mode has no intraday constraint.
        results = engine.get_results()
        assert isinstance(results, dict)
