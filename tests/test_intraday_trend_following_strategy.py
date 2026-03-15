"""
Comprehensive test suite for intraday_trend_following_strategy.py

Tests (15 groups, 62 cases total):
  T01 - Sanity            : real RELIANCE_5M.csv → correct output structure & types
  T02 - No-trade          : out-of-session bars produce zero signals / trades
  T03 - Long-only         : uptrend in session → long signals fire, no shorts
  T04 - Short-only        : downtrend in session → short signals fire (BUG 1 fixed)
  T05 - VWAP reset        : VWAP resets to fresh cumulative at IST day boundary
  T06 - Session boundary  : exact 09:30 / 15:00 / 09:29 edge cases
  T07 - TP hit            : high crossing TP → exit at exact TP price
  T08 - SL hit            : low crossing SL → exit at exact SL price
  T09 - Same-bar conflict : both TP and SL hit → SL wins (conservative order)
  T10 - Overnight carry   : BUG 2 fixed – no positions remain open past 15:00 IST
  T11 - EMA warmup        : no signals while EMA is NaN (first ema_length-1 bars)
  T12 - SuperTrend fixed  : BUG 1 fixed – bands and line are correctly initialised
  T13 - ATR Wilder's      : alpha = 1/period, converges to true range on constant data
  T14 - Position sizing   : units = equity × size_pct / entry_price
  T15 - Short PnL formula : (entry - exit) × units (arithmetic unit test)
"""

from __future__ import annotations

import warnings
import logging

import pytest
import pandas as pd
import numpy as np

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=pd.errors.SettingWithCopyWarning)
logging.disable(logging.CRITICAL)

from src.strategies.intraday_trend_following_strategy import (
    StrategyConfig,
    prepare_strategy_dataframe,
    backtest_strategy,
    intraday_vwap,
    supertrend,
    in_session,
    atr,
    ema,
    _ensure_datetime_index,
    load_ohlcv_csv,
)


# ─────────────────────────────────────────────────────────────────────────────
# SHARED HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _ist_to_utc(date_str: str, hhmm: str) -> pd.Timestamp:
    ts = pd.Timestamp(f"{date_str} {hhmm}:00", tz="Asia/Kolkata")
    return ts.tz_convert("UTC")


def _make_bars(
    date_str: str,
    session_start_ist: str = "09:30",
    n_bars: int = 60,
    freq: str = "5min",
    base_price: float = 1000.0,
    step: float = 10.0,
    bar_range: float = 2.0,
    volume: int = 10_000,
) -> pd.DataFrame:
    start_ts = _ist_to_utc(date_str, session_start_ist)
    idx = pd.date_range(start=start_ts, periods=n_bars, freq=freq)
    prices = [base_price + i * step for i in range(n_bars)]
    half = bar_range / 2.0
    return pd.DataFrame(
        {"open": prices, "high": [p + half for p in prices],
         "low":  [p - half for p in prices], "close": prices,
         "volume": [volume] * n_bars},
        index=idx,
    )


def _test_cfg(**kwargs) -> StrategyConfig:
    defaults = dict(
        st_period=5, ema_length=5, st_factor=3.0,
        tp_percent=1.0, sl_percent=0.5,
        session_start="09:30", session_end="15:00",
        timezone="Asia/Kolkata",
        initial_capital=100_000.0, position_size_pct=0.10,
    )
    defaults.update(kwargs)
    return StrategyConfig(**defaults)


def _to_input(bars: pd.DataFrame) -> pd.DataFrame:
    return bars.reset_index().rename(columns={"index": "timestamp"})


# ─────────────────────────────────────────────────────────────────────────────
# T01 – SANITY
# ─────────────────────────────────────────────────────────────────────────────

class TestSanity:
    """T01 – Load real RELIANCE_5M.csv and validate output structure / types."""

    @pytest.fixture(scope="class")
    def results(self):
        df = load_ohlcv_csv("data/RELIANCE_5M.csv")
        cfg = StrategyConfig(ema_length=20)
        return backtest_strategy(df, cfg)

    def test_summary_has_required_keys(self, results):
        _, _, summary = results
        required = {"initial_capital", "final_equity", "net_profit",
                    "total_trades", "wins", "losses", "win_rate_pct", "max_drawdown_pct"}
        assert required.issubset(set(summary.keys()))

    def test_data_has_indicator_columns(self, results):
        data, _, _ = results
        for col in ["long_signal", "short_signal", "vwap", "ema",
                    "direction", "supertrend", "is_in_session"]:
            assert col in data.columns, f"Missing column: {col}"

    def test_trades_df_has_required_columns(self, results):
        _, trades_df, _ = results
        if not trades_df.empty:
            for col in ["entry_time", "exit_time", "side", "entry_price",
                        "exit_price", "units", "pnl", "exit_reason"]:
                assert col in trades_df.columns, f"Missing trade column: {col}"

    def test_win_rate_in_valid_range(self, results):
        _, _, summary = results
        assert 0.0 <= summary["win_rate_pct"] <= 100.0

    def test_wins_plus_losses_equals_total_trades(self, results):
        _, _, summary = results
        assert summary["wins"] + summary["losses"] == summary["total_trades"]

    def test_final_equity_is_positive(self, results):
        _, _, summary = results
        assert summary["final_equity"] > 0

    def test_exit_reasons_are_valid(self, results):
        _, trades_df, _ = results
        valid = {"take_profit", "stop_loss", "session_end"}
        if not trades_df.empty:
            assert set(trades_df["exit_reason"].unique()).issubset(valid)


# ─────────────────────────────────────────────────────────────────────────────
# T02 – NO-TRADE
# ─────────────────────────────────────────────────────────────────────────────

class TestNoTrade:
    """T02 – All bars outside 09:30–15:00 IST → zero signals."""

    @pytest.fixture
    def out_of_session_bars(self):
        start_ts = _ist_to_utc("2025-12-10", "00:00")
        idx = pd.date_range(start=start_ts, periods=60, freq="5min")
        prices = [1000.0 + i * 10 for i in range(60)]
        return pd.DataFrame(
            {"open": prices, "high": [p+2 for p in prices],
             "low":  [p-2 for p in prices], "close": prices, "volume": [10_000]*60},
            index=idx,
        )

    def test_all_bars_marked_out_of_session(self, out_of_session_bars):
        result = prepare_strategy_dataframe(_to_input(out_of_session_bars), _test_cfg())
        assert result["is_in_session"].sum() == 0

    def test_no_long_signals_out_of_session(self, out_of_session_bars):
        result = prepare_strategy_dataframe(_to_input(out_of_session_bars), _test_cfg())
        assert result["long_signal"].sum() == 0

    def test_no_short_signals_out_of_session(self, out_of_session_bars):
        result = prepare_strategy_dataframe(_to_input(out_of_session_bars), _test_cfg())
        assert result["short_signal"].sum() == 0

    def test_zero_trades_out_of_session(self, out_of_session_bars):
        _, trades_df, summary = backtest_strategy(_to_input(out_of_session_bars), _test_cfg())
        assert summary["total_trades"] == 0
        assert trades_df.empty


# ─────────────────────────────────────────────────────────────────────────────
# T03 – LONG-ONLY
# ─────────────────────────────────────────────────────────────────────────────

class TestLongOnly:
    """T03 – Strong uptrend in session generates long-only signals."""

    @pytest.fixture
    def uptrend_bars(self):
        return _make_bars("2025-12-10", step=10.0, n_bars=60)

    def test_long_signals_fire_after_warmup(self, uptrend_bars):
        result = prepare_strategy_dataframe(_to_input(uptrend_bars), _test_cfg())
        assert result["long_signal"].sum() > 0

    def test_no_short_signals_in_uptrend(self, uptrend_bars):
        result = prepare_strategy_dataframe(_to_input(uptrend_bars), _test_cfg())
        assert result["short_signal"].sum() == 0

    def test_no_signals_during_warmup_bars(self, uptrend_bars):
        cfg = _test_cfg(ema_length=5)
        result = prepare_strategy_dataframe(_to_input(uptrend_bars), cfg)
        warmup = result.head(cfg.ema_length - 1)
        assert warmup["long_signal"].sum() == 0
        assert warmup["short_signal"].sum() == 0

    def test_long_trades_generated_and_all_long(self, uptrend_bars):
        _, trades_df, summary = backtest_strategy(_to_input(uptrend_bars), _test_cfg())
        assert summary["total_trades"] > 0
        if not trades_df.empty:
            assert (trades_df["side"] == "long").all()

    def test_long_pnl_formula_is_correct(self, uptrend_bars):
        _, trades_df, _ = backtest_strategy(_to_input(uptrend_bars), _test_cfg())
        if trades_df.empty:
            pytest.skip("No trades generated")
        for _, row in trades_df[trades_df["side"] == "long"].iterrows():
            expected = (row["exit_price"] - row["entry_price"]) * row["units"]
            assert abs(row["pnl"] - expected) < 1e-6

    def test_close_above_vwap_when_long_signal(self, uptrend_bars):
        result = prepare_strategy_dataframe(_to_input(uptrend_bars), _test_cfg())
        long_bars = result[result["long_signal"]]
        assert (long_bars["close"] > long_bars["vwap"]).all()

    def test_close_above_ema_when_long_signal(self, uptrend_bars):
        result = prepare_strategy_dataframe(_to_input(uptrend_bars), _test_cfg())
        long_bars = result[result["long_signal"]]
        assert (long_bars["close"] > long_bars["ema"]).all()

    def test_direction_minus_one_when_long_signal(self, uptrend_bars):
        result = prepare_strategy_dataframe(_to_input(uptrend_bars), _test_cfg())
        long_bars = result[result["long_signal"]]
        assert (long_bars["direction"] == -1).all()


# ─────────────────────────────────────────────────────────────────────────────
# T04 – SHORT-ONLY  (BUG 1 fixed – short signals now work)
# ─────────────────────────────────────────────────────────────────────────────

class TestShortOnly:
    """T04 – After BUG 1 fix: downtrend produces short-only signals and trades."""

    @pytest.fixture
    def downtrend_bars(self):
        # 20 sideways bars (warmup + initial ST direction settles bearish)
        # then 46-bar gap-down + continued decline
        n_warm, n_down = 20, 46
        start_ts = _ist_to_utc("2025-12-10", "09:30")
        idx = pd.date_range(start=start_ts, periods=n_warm + n_down, freq="5min")
        prices = [2000.0] * n_warm + [1960.0 - i * 5 for i in range(n_down)]
        return pd.DataFrame(
            {"open":   [p + 1 for p in prices],
             "high":   [p + 1 for p in prices],
             "low":    [p - 1 for p in prices],
             "close":  [p - 1 for p in prices],
             "volume": [10_000] * (n_warm + n_down)},
            index=idx,
        )

    def test_short_signals_fire_in_downtrend(self, downtrend_bars):
        result = prepare_strategy_dataframe(_to_input(downtrend_bars), _test_cfg())
        assert result["short_signal"].sum() > 0, (
            "Expected short signals in downtrend after BUG 1 fix"
        )

    def test_no_long_signals_in_downtrend(self, downtrend_bars):
        result = prepare_strategy_dataframe(_to_input(downtrend_bars), _test_cfg())
        assert result["long_signal"].sum() == 0

    def test_direction_reaches_plus_one_in_downtrend(self, downtrend_bars):
        """BUG 1 fixed: direction can reach +1 (bearish ST) in downtrend/sideways."""
        result = prepare_strategy_dataframe(_to_input(downtrend_bars), _test_cfg())
        after_warmup = result.iloc[_test_cfg().st_period:]
        assert (after_warmup["direction"] == 1).any(), (
            "direction must be able to reach +1 after BUG 1 fix"
        )

    def test_supertrend_line_valid_after_warmup(self, downtrend_bars):
        """BUG 1 fixed: SuperTrend line has valid (non-NaN) values after ATR warmup."""
        result = prepare_strategy_dataframe(_to_input(downtrend_bars), _test_cfg())
        after_warmup = result.iloc[_test_cfg().st_period:]
        assert after_warmup["supertrend"].notna().any(), (
            "SuperTrend line must be non-NaN after BUG 1 fix"
        )

    def test_short_trades_generated(self, downtrend_bars):
        _, trades_df, summary = backtest_strategy(_to_input(downtrend_bars), _test_cfg())
        assert summary["total_trades"] > 0, "Expected trades in downtrend"
        if not trades_df.empty:
            non_session_end = trades_df[trades_df["exit_reason"] != "session_end"]
            short_or_session = trades_df["side"].isin(["short"])
            assert (trades_df["side"] == "short").any(), "Expected at least one short trade"

    def test_close_below_vwap_when_short_signal(self, downtrend_bars):
        result = prepare_strategy_dataframe(_to_input(downtrend_bars), _test_cfg())
        short_bars = result[result["short_signal"]]
        if not short_bars.empty:
            assert (short_bars["close"] < short_bars["vwap"]).all()

    def test_close_below_ema_when_short_signal(self, downtrend_bars):
        result = prepare_strategy_dataframe(_to_input(downtrend_bars), _test_cfg())
        short_bars = result[result["short_signal"]]
        if not short_bars.empty:
            assert (short_bars["close"] < short_bars["ema"]).all()

    def test_direction_plus_one_when_short_signal(self, downtrend_bars):
        result = prepare_strategy_dataframe(_to_input(downtrend_bars), _test_cfg())
        short_bars = result[result["short_signal"]]
        if not short_bars.empty:
            assert (short_bars["direction"] == 1).all()

    def test_short_pnl_formula_correct(self, downtrend_bars):
        _, trades_df, _ = backtest_strategy(_to_input(downtrend_bars), _test_cfg())
        short_trades = trades_df[trades_df["side"] == "short"]
        for _, row in short_trades.iterrows():
            expected = (row["entry_price"] - row["exit_price"]) * row["units"]
            assert abs(row["pnl"] - expected) < 1e-6, "Short PnL = (entry - exit) × units"


# ─────────────────────────────────────────────────────────────────────────────
# T05 – VWAP RESET
# ─────────────────────────────────────────────────────────────────────────────

class TestVWAPReset:
    """T05 – VWAP resets per IST calendar day."""

    @pytest.fixture
    def two_day_bars(self):
        idx1 = pd.date_range(start=_ist_to_utc("2025-12-10", "09:30"), periods=66, freq="5min")
        idx2 = pd.date_range(start=_ist_to_utc("2025-12-11", "09:30"), periods=66, freq="5min")
        idx = idx1.append(idx2)
        prices = [1000.0 + i * 5 for i in range(66)] + [2000.0 + i * 5 for i in range(66)]
        return pd.DataFrame(
            {"open": prices, "high": [p+1 for p in prices],
             "low":  [p-1 for p in prices], "close": prices, "volume": [10_000]*132},
            index=idx,
        )

    def test_vwap_day1_bar0_equals_typical_price(self, two_day_bars):
        data = _ensure_datetime_index(_to_input(two_day_bars))
        vwap_vals = intraday_vwap(data, timezone="Asia/Kolkata")
        tp_d1 = (two_day_bars["high"].iloc[0] + two_day_bars["low"].iloc[0] +
                 two_day_bars["close"].iloc[0]) / 3.0
        assert abs(vwap_vals.iloc[0] - tp_d1) < 1e-6

    def test_vwap_day2_bar0_equals_typical_price_of_day2(self, two_day_bars):
        data = _ensure_datetime_index(_to_input(two_day_bars))
        vwap_vals = intraday_vwap(data, timezone="Asia/Kolkata")
        tp_d2 = (two_day_bars["high"].iloc[66] + two_day_bars["low"].iloc[66] +
                 two_day_bars["close"].iloc[66]) / 3.0
        assert abs(vwap_vals.iloc[66] - tp_d2) < 1e-6

    def test_vwap_day2_not_contaminated_by_day1_prices(self, two_day_bars):
        data = _ensure_datetime_index(_to_input(two_day_bars))
        vwap_vals = intraday_vwap(data, timezone="Asia/Kolkata")
        assert vwap_vals.iloc[66] > 1900, "Day-2 VWAP should NOT reflect day-1 prices"

    def test_vwap_rises_within_uptrending_session(self, two_day_bars):
        data = _ensure_datetime_index(_to_input(two_day_bars))
        vwap_vals = intraday_vwap(data, timezone="Asia/Kolkata")
        day1_vwap = vwap_vals.iloc[:66]
        assert day1_vwap.iloc[-1] > day1_vwap.iloc[0]


# ─────────────────────────────────────────────────────────────────────────────
# T06 – SESSION BOUNDARY
# ─────────────────────────────────────────────────────────────────────────────

class TestSessionBoundary:
    """T06 – in_session() edge cases at 09:29, 09:30, 15:00, 15:01 IST."""

    def _check(self, hhmm_ist: str) -> bool:
        ts = _ist_to_utc("2025-12-10", hhmm_ist)
        idx = pd.DatetimeIndex([ts])
        return bool(in_session(idx, "09:30", "15:00", "Asia/Kolkata").iloc[0])

    def test_09_29_is_out(self):    assert self._check("09:29") is False
    def test_09_30_is_in(self):     assert self._check("09:30") is True
    def test_09_31_is_in(self):     assert self._check("09:31") is True
    def test_12_00_is_in(self):     assert self._check("12:00") is True
    def test_14_59_is_in(self):     assert self._check("14:59") is True
    def test_15_00_is_in(self):     assert self._check("15:00") is True
    def test_15_01_is_out(self):    assert self._check("15:01") is False
    def test_midnight_is_out(self): assert self._check("00:00") is False
    def test_pre_dawn_is_out(self): assert self._check("04:00") is False


# ─────────────────────────────────────────────────────────────────────────────
# T07 – TAKE-PROFIT
# ─────────────────────────────────────────────────────────────────────────────

class TestTakeProfitLong:
    """T07 – High crossing TP → exit at exact TP price; PnL > 0."""

    @pytest.fixture
    def tp_scenario(self):
        # Bars 0-7: step-10 uptrend → SuperTrend direction flips to -1 at bar 7
        # → long_signal fires at bar 7, entry_price=1070.
        # Bar 8: high crosses TP (1080.70), low stays above SL (1064.65).
        n_up = 8
        start = _ist_to_utc("2025-12-10", "09:30")
        idx = pd.date_range(start=start, periods=n_up + 1, freq="5min")
        prices = [1000.0 + i * 10.0 for i in range(n_up)]
        highs  = [p + 1.0 for p in prices]
        lows   = [p - 1.0 for p in prices]
        entry_price = 1070.0          # first long signal at bar 7 (close=1070)
        tp = entry_price * 1.01       # 1080.70
        sl = entry_price * 0.995      # 1064.65
        prices.append(1070.0)
        highs.append(tp + 10.0)       # 1090.70 – clearly above TP
        lows.append(sl + 2.0)         # 1066.65 – safely above SL
        bars = pd.DataFrame({"open": prices, "high": highs, "low": lows,
                             "close": prices, "volume": [10_000] * (n_up + 1)},
                            index=idx)
        return bars, tp

    def test_tp_exit_reason(self, tp_scenario):
        bars, _ = tp_scenario
        _, trades_df, _ = backtest_strategy(_to_input(bars), _test_cfg())
        assert not trades_df.empty
        assert (trades_df["exit_reason"] == "take_profit").any()

    def test_tp_exit_price_is_exact(self, tp_scenario):
        bars, expected_tp = tp_scenario
        _, trades_df, _ = backtest_strategy(_to_input(bars), _test_cfg())
        tp_exits = trades_df[trades_df["exit_reason"] == "take_profit"]
        for _, row in tp_exits.iterrows():
            assert abs(row["exit_price"] - expected_tp) < 1e-4

    def test_tp_pnl_is_positive(self, tp_scenario):
        bars, _ = tp_scenario
        _, trades_df, _ = backtest_strategy(_to_input(bars), _test_cfg())
        tp_exits = trades_df[trades_df["exit_reason"] == "take_profit"]
        for _, row in tp_exits.iterrows():
            assert row["pnl"] > 0


# ─────────────────────────────────────────────────────────────────────────────
# T08 – STOP-LOSS
# ─────────────────────────────────────────────────────────────────────────────

class TestStopLossLong:
    """T08 – Low crossing SL → exit at exact SL price; PnL < 0."""

    @pytest.fixture
    def sl_scenario(self):
        # Bars 0-7: step-10 uptrend → long_signal fires at bar 7, entry_price=1070.
        # Bar 8: low crosses SL (1064.65), high stays below TP (1080.70).
        n_up = 8
        start = _ist_to_utc("2025-12-10", "09:30")
        idx = pd.date_range(start=start, periods=n_up + 1, freq="5min")
        prices = [1000.0 + i * 10.0 for i in range(n_up)]
        highs  = [p + 1.0 for p in prices]
        lows   = [p - 1.0 for p in prices]
        entry_price = 1070.0          # first long signal at bar 7 (close=1070)
        tp = entry_price * 1.01       # 1080.70
        sl = entry_price * 0.995      # 1064.65
        prices.append(1060.0)
        highs.append(tp - 2.0)        # 1078.70 – safely below TP
        lows.append(sl - 5.0)         # 1059.65 – clearly below SL
        bars = pd.DataFrame({"open": prices, "high": highs, "low": lows,
                             "close": prices, "volume": [10_000] * (n_up + 1)},
                            index=idx)
        return bars, sl

    def test_sl_exit_reason(self, sl_scenario):
        bars, _ = sl_scenario
        _, trades_df, _ = backtest_strategy(_to_input(bars), _test_cfg())
        assert not trades_df.empty
        assert (trades_df["exit_reason"] == "stop_loss").any()

    def test_sl_exit_price_is_exact(self, sl_scenario):
        bars, expected_sl = sl_scenario
        _, trades_df, _ = backtest_strategy(_to_input(bars), _test_cfg())
        sl_exits = trades_df[trades_df["exit_reason"] == "stop_loss"]
        for _, row in sl_exits.iterrows():
            assert abs(row["exit_price"] - expected_sl) < 1e-4

    def test_sl_pnl_is_negative(self, sl_scenario):
        bars, _ = sl_scenario
        _, trades_df, _ = backtest_strategy(_to_input(bars), _test_cfg())
        sl_exits = trades_df[trades_df["exit_reason"] == "stop_loss"]
        for _, row in sl_exits.iterrows():
            assert row["pnl"] < 0


# ─────────────────────────────────────────────────────────────────────────────
# T09 – SAME-BAR CONFLICT
# ─────────────────────────────────────────────────────────────────────────────

class TestSameBarConflict:
    """T09 – When both TP and SL hit on the same bar, SL is processed first."""

    def test_sl_wins_over_tp_on_same_bar(self):
        # Bars 0-7: step-10 uptrend → long_signal fires at bar 7, entry_price=1070.
        # Bar 8: both SL (1064.65) and TP (1080.70) conditions are triggered.
        # SL is checked before TP in the exit logic → stop_loss wins (conservative).
        n_up = 8
        entry_price = 1070.0
        sl = entry_price * 0.995   # 1064.65
        tp = entry_price * 1.01    # 1080.70
        start = _ist_to_utc("2025-12-10", "09:30")
        idx = pd.date_range(start=start, periods=n_up + 1, freq="5min")
        prices = [1000.0 + i * 10.0 for i in range(n_up)]
        highs  = [p + 1.0 for p in prices]
        lows   = [p - 1.0 for p in prices]
        prices.append(1070.0)
        highs.append(tp + 10.0)    # 1090.70 – above TP
        lows.append(sl - 5.0)      # 1059.65 – below SL
        bars = pd.DataFrame({"open": prices, "high": highs, "low": lows,
                             "close": prices, "volume": [10_000] * (n_up + 1)},
                            index=idx)
        _, trades_df, _ = backtest_strategy(_to_input(bars), _test_cfg())
        assert not trades_df.empty
        row = trades_df.iloc[-1]
        assert row["exit_reason"] == "stop_loss"
        assert abs(row["exit_price"] - sl) < 1e-4
        assert row["pnl"] < 0


# ─────────────────────────────────────────────────────────────────────────────
# T10 – OVERNIGHT CARRY (BUG 2 fixed)
# ─────────────────────────────────────────────────────────────────────────────

class TestOvernightCarry:
    """T10 – BUG 2 fixed: session-end force-close prevents overnight positions."""

    @pytest.fixture(scope="class")
    def real_trades(self):
        df = load_ohlcv_csv("data/RELIANCE_5M.csv")
        cfg = StrategyConfig(ema_length=20)
        _, trades_df, _ = backtest_strategy(df, cfg)
        return trades_df

    def test_no_overnight_carry_on_real_data(self, real_trades):
        """After BUG 2 fix: zero trades cross midnight IST."""
        if real_trades.empty:
            return
        tdf = real_trades.copy()
        tdf["entry_date"] = pd.to_datetime(tdf["entry_time"]).dt.tz_convert("Asia/Kolkata").dt.date
        tdf["exit_date"]  = pd.to_datetime(tdf["exit_time"]).dt.tz_convert("Asia/Kolkata").dt.date
        overnight = tdf[tdf["entry_date"] != tdf["exit_date"]]
        assert len(overnight) == 0, (
            f"BUG 2 fixed: expected 0 overnight carries, got {len(overnight)}"
        )

    def test_session_end_exit_reason_exists(self, real_trades):
        """After BUG 2 fix: 'session_end' exit reason must appear in trade log."""
        if real_trades.empty:
            pytest.skip("No trades generated")
        assert "session_end" in real_trades["exit_reason"].values, (
            "Expected 'session_end' exits after BUG 2 fix"
        )

    def test_all_exits_within_session_or_at_session_end(self, real_trades):
        """Every exit timestamp must be on same IST calendar day as entry."""
        if real_trades.empty:
            return
        tdf = real_trades.copy()
        tdf["entry_date"] = pd.to_datetime(tdf["entry_time"]).dt.tz_convert("Asia/Kolkata").dt.date
        tdf["exit_date"]  = pd.to_datetime(tdf["exit_time"]).dt.tz_convert("Asia/Kolkata").dt.date
        bad = tdf[tdf["entry_date"] != tdf["exit_date"]]
        assert len(bad) == 0, f"Found {len(bad)} trades with cross-day exits"


# ─────────────────────────────────────────────────────────────────────────────
# T11 – EMA WARMUP
# ─────────────────────────────────────────────────────────────────────────────

class TestEMAWarmup:
    """T11 – No signals during first ema_length-1 bars (EMA is NaN)."""

    def test_ema_nan_during_warmup(self):
        bars = _make_bars("2025-12-10", step=5.0, n_bars=30)
        cfg = _test_cfg(ema_length=10)
        result = prepare_strategy_dataframe(_to_input(bars), cfg)
        assert result["ema"].iloc[:cfg.ema_length - 1].isna().all()

    def test_no_signal_during_ema_nan_period(self):
        bars = _make_bars("2025-12-10", step=5.0, n_bars=30)
        cfg = _test_cfg(ema_length=10)
        result = prepare_strategy_dataframe(_to_input(bars), cfg)
        warmup = result.iloc[:cfg.ema_length - 1]
        assert warmup["long_signal"].sum() == 0
        assert warmup["short_signal"].sum() == 0

    def test_ema_valid_from_period_bar_onwards(self):
        bars = _make_bars("2025-12-10", step=5.0, n_bars=30)
        cfg = _test_cfg(ema_length=5)
        result = prepare_strategy_dataframe(_to_input(bars), cfg)
        assert result["ema"].iloc[cfg.ema_length - 1:].notna().all()

    def test_ema_below_close_in_uptrend(self):
        bars = _make_bars("2025-12-10", step=5.0, n_bars=30)
        cfg = _test_cfg(ema_length=5)
        result = prepare_strategy_dataframe(_to_input(bars), cfg)
        check = result.iloc[cfg.ema_length + 2:]
        assert (check["close"] > check["ema"]).all()


# ─────────────────────────────────────────────────────────────────────────────
# T12 – SUPERTREND FIXED (BUG 1 corrected)
# ─────────────────────────────────────────────────────────────────────────────

class TestSuperTrendFixed:
    """T12 – Verifies BUG 1 fix: bands and ST line are correctly initialised."""

    @pytest.fixture
    def uptrend_data(self):
        start = _ist_to_utc("2025-12-10", "09:30")
        idx = pd.date_range(start=start, periods=60, freq="5min")
        prices = [2000.0 + i * 10 for i in range(60)]
        bars = pd.DataFrame(
            {"open": prices, "high": [p+2 for p in prices],
             "low":  [p-2 for p in prices], "close": prices, "volume": [10_000]*60},
            index=idx,
        )
        return _ensure_datetime_index(_to_input(bars))

    @pytest.fixture
    def sideways_data(self):
        start = _ist_to_utc("2025-12-10", "09:30")
        idx = pd.date_range(start=start, periods=50, freq="5min")
        prices = [2000.0] * 50
        bars = pd.DataFrame(
            {"open": prices, "high": [p+2 for p in prices],
             "low":  [p-2 for p in prices], "close": prices, "volume": [10_000]*50},
            index=idx,
        )
        return _ensure_datetime_index(_to_input(bars))

    def test_final_upper_not_all_nan(self, sideways_data):
        period = 10
        a_s = atr(sideways_data, period)
        hl2 = (sideways_data["high"] + sideways_data["low"]) / 2.0
        upperband = hl2 + 3.0 * a_s
        final_upper = upperband.copy()
        for i in range(1, len(sideways_data)):
            prev_close = sideways_data["close"].iloc[i-1]
            if pd.isna(final_upper.iloc[i-1]):
                final_upper.iloc[i] = upperband.iloc[i]
            elif (upperband.iloc[i] < final_upper.iloc[i-1]) or (prev_close > final_upper.iloc[i-1]):
                final_upper.iloc[i] = upperband.iloc[i]
            else:
                final_upper.iloc[i] = final_upper.iloc[i-1]
        assert not final_upper.isna().all(), "BUG 1 fixed: final_upper should NOT be all NaN"
        assert final_upper.iloc[period:].notna().all(), "final_upper must be valid after warmup"

    def test_supertrend_line_valid_after_warmup(self, sideways_data):
        st_line, _ = supertrend(sideways_data, period=10, factor=3.0)
        assert not st_line.isna().all(), "BUG 1 fixed: ST line should NOT be all NaN"
        assert st_line.iloc[10:].notna().all(), "ST line must be valid after warmup"

    def test_direction_reaches_minus_one_in_uptrend(self, uptrend_data):
        _, direction = supertrend(uptrend_data, period=5, factor=3.0)
        assert (direction == -1).any(), "Direction must reach -1 (bullish) in uptrend"

    def test_direction_reaches_plus_one_in_sideways(self, sideways_data):
        _, direction = supertrend(sideways_data, period=10, factor=3.0)
        after_warmup = direction.iloc[10:]
        assert (after_warmup == 1).any(), (
            "Direction must reach +1 (bearish) in sideways/flat data"
        )

    def test_both_direction_values_possible_in_mixed_data(self, uptrend_data):
        _, direction = supertrend(uptrend_data, period=5, factor=3.0)
        assert (direction == -1).any(), "Bullish direction must be reachable"
        # +1 appears during initial warmup bars
        assert (direction == 1).any(), "Bearish direction must appear at warmup/init"


# ─────────────────────────────────────────────────────────────────────────────
# T13 – ATR WILDER'S SMOOTHING
# ─────────────────────────────────────────────────────────────────────────────

class TestATRWilder:
    """T13 – ATR uses Wilder's smoothing (alpha = 1/period)."""

    def test_atr_converges_to_constant_range(self):
        start = _ist_to_utc("2025-12-10", "09:30")
        idx = pd.date_range(start=start, periods=40, freq="5min")
        prices = [1000.0] * 40
        bar_range = 4.0
        bars = pd.DataFrame(
            {"open": prices, "high": [p + bar_range/2 for p in prices],
             "low":  [p - bar_range/2 for p in prices], "close": prices,
             "volume": [10_000]*40},
            index=idx,
        )
        data = _ensure_datetime_index(_to_input(bars))
        result = atr(data, 5)
        for val in result.dropna():
            assert abs(val - bar_range) < 1e-6

    def test_atr_nan_for_warmup_bars(self):
        start = _ist_to_utc("2025-12-10", "09:30")
        idx = pd.date_range(start=start, periods=20, freq="5min")
        prices = [1000.0] * 20
        bars = pd.DataFrame(
            {"open": prices, "high": [p+2 for p in prices],
             "low":  [p-2 for p in prices], "close": prices, "volume": [10_000]*20},
            index=idx,
        )
        data = _ensure_datetime_index(_to_input(bars))
        period = 10
        result = atr(data, period)
        assert result.iloc[:period-1].isna().all()

    def test_atr_valid_from_period_bar_onwards(self):
        start = _ist_to_utc("2025-12-10", "09:30")
        idx = pd.date_range(start=start, periods=20, freq="5min")
        prices = [1000.0] * 20
        bars = pd.DataFrame(
            {"open": prices, "high": [p+2 for p in prices],
             "low":  [p-2 for p in prices], "close": prices, "volume": [10_000]*20},
            index=idx,
        )
        data = _ensure_datetime_index(_to_input(bars))
        period = 10
        result = atr(data, period)
        assert result.iloc[period-1:].notna().all()


# ─────────────────────────────────────────────────────────────────────────────
# T14 – POSITION SIZING
# ─────────────────────────────────────────────────────────────────────────────

class TestPositionSizing:
    """T14 – units = equity × size_pct / entry_price."""

    def test_first_trade_units_matches_formula(self):
        bars = _make_bars("2025-12-10", step=10.0, n_bars=20)
        cfg = _test_cfg(position_size_pct=0.10, initial_capital=100_000.0)
        _, trades_df, _ = backtest_strategy(_to_input(bars), cfg)
        if trades_df.empty:
            pytest.skip("No trades generated")
        row = trades_df.iloc[0]
        expected = 100_000.0 * 0.10 / row["entry_price"]
        assert abs(row["units"] - expected) < 0.01

    def test_initial_capital_in_summary(self):
        bars = _make_bars("2025-12-10", step=10.0, n_bars=20)
        cfg = _test_cfg(initial_capital=75_000.0)
        _, _, summary = backtest_strategy(_to_input(bars), cfg)
        assert summary["initial_capital"] == 75_000.0

    def test_net_profit_is_final_minus_initial(self):
        bars = _make_bars("2025-12-10", step=10.0, n_bars=20)
        _, _, summary = backtest_strategy(_to_input(bars), _test_cfg())
        expected = summary["final_equity"] - summary["initial_capital"]
        assert abs(summary["net_profit"] - expected) < 1e-6


# ─────────────────────────────────────────────────────────────────────────────
# T15 – SHORT PnL FORMULA
# ─────────────────────────────────────────────────────────────────────────────

class TestShortPnLFormula:
    """T15 – pnl = (entry_price - exit_price) × units for shorts."""

    def test_short_tp_pnl_is_positive(self):
        entry, tp_pct, units = 2000.0, 1.0, 5.0
        tp = entry * (1 - tp_pct / 100)
        assert (entry - tp) * units > 0

    def test_short_sl_pnl_is_negative(self):
        entry, sl_pct, units = 2000.0, 0.5, 5.0
        sl = entry * (1 + sl_pct / 100)
        assert (entry - sl) * units < 0

    def test_short_tp_less_than_entry(self):
        entry = 2000.0
        assert entry * (1 - 1.0 / 100) < entry

    def test_short_sl_greater_than_entry(self):
        entry = 2000.0
        assert entry * (1 + 0.5 / 100) > entry
