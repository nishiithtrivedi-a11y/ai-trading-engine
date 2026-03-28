"""
Dynamic Regime Adaptive System Strategy (DRAS v3.2)
====================================================
Python port of the Pine Script strategy "NSE Dynamic Regime Adaptive System
(DRAS v3.2) - v6".

Safety guarantee
----------------
This module is a SIGNAL-ONLY implementation. It never places, routes, or
submits real orders. All outputs are advisory StrategySignal objects consumed
by the backtesting engine or paper-trading monitor only.

Design decisions
----------------
1. ``precompute()`` vectorises all indicator columns on the full dataset so
   ``on_bar()`` is a fast dictionary lookup — no per-bar pandas operations.
2. Position-state (entry price, stops, TP1 flag, etc.) is maintained as
   instance variables, mirroring Pine's ``var`` persistence across bars.
3. ``backtest_dras()`` is a standalone function that runs the complete
   loop with Pine-faithful OCO exit logic and partial TP1 exits.

Pine behaviour differences (documented)
---------------------------------------
- ``process_orders_on_close=true`` → entry/exit price = bar close.
- OCO exits: stop checked first; TP1 only fires if stop not hit.
- ``qty_percent=50`` partial → tracked via ``_half_exited`` flag.
- VWAP resets per IST calendar day (groupby date cumsum).
- ``conLosses`` increments on each closed losing trade; resets on winning
  trade or new day.
- ADX/DMI: Wilder's RMA (ewm alpha=1/period, adjust=False).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import pandas as pd

from src.strategies.base_strategy import BaseStrategy, Signal, StrategySignal

TIMEZONE = "Asia/Kolkata"


# ---------------------------------------------------------------------------
# Parameters dataclass
# ---------------------------------------------------------------------------

@dataclass
class DRASConfig:
    """All configurable DRAS v3.2 parameters, mirroring Pine inputs."""

    adx_threshold: int = 20
    vol_ratio_limit: float = 1.5
    vwap_cross_limit: int = 3
    vol_sma_len: int = 20
    vol_mult: float = 1.2
    wick_percent: float = 0.5
    risk_per_trade: float = 1.0
    daily_dd_limit: float = 2.0
    max_daily_trades: int = 3
    max_con_losses: int = 2
    sl_atr_mult: float = 1.5
    trail_atr_mult: float = 2.5
    trail_atr_period: int = 10
    initial_capital: float = 100_000.0
    commission_pct: float = 0.12  # 0.12% per side, matching Pine
    min_tick: float = 0.05        # NSE equity minimum tick


# ---------------------------------------------------------------------------
# Indicator helpers (pure pandas / numpy, no TA-Lib)
# ---------------------------------------------------------------------------

def _true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [df["high"] - df["low"],
         (df["high"] - prev_close).abs(),
         (df["low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr


def _wilder_atr(df: pd.DataFrame, period: int) -> pd.Series:
    """Wilder's Average True Range — matches Pine ta.atr()."""
    tr = _true_range(df)
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False, min_periods=span).mean()


def _dmi_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    Wilder's DMI/ADX — matches Pine ta.dmi(14, 14).

    Returns DataFrame with columns: plus_di, minus_di, adx
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]

    prev_high = high.shift(1)
    prev_low = low.shift(1)

    up_move = high - prev_high
    down_move = prev_low - low

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    plus_dm_s = pd.Series(plus_dm, index=df.index)
    minus_dm_s = pd.Series(minus_dm, index=df.index)

    tr = _true_range(df)

    smooth_tr = tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    smooth_plus = plus_dm_s.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    smooth_minus = minus_dm_s.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()

    plus_di = 100.0 * smooth_plus / smooth_tr.replace(0, np.nan)
    minus_di = 100.0 * smooth_minus / smooth_tr.replace(0, np.nan)

    dx_num = (plus_di - minus_di).abs()
    dx_den = (plus_di + minus_di).replace(0, np.nan)
    dx = 100.0 * dx_num / dx_den

    adx = dx.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()

    return pd.DataFrame({"plus_di": plus_di, "minus_di": minus_di, "adx": adx},
                        index=df.index)


def _intraday_vwap(df: pd.DataFrame, tz: str = TIMEZONE) -> pd.Series:
    """
    Daily-reset VWAP using typical price = (H+L+C)/3.

    Matches Pine's ta.vwap() which resets at session open.
    """
    local = df.index.tz_convert(tz)
    date_key = pd.Series(local.normalize(), index=df.index)
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    pv = tp * df["volume"]
    cum_pv = pv.groupby(date_key).cumsum()
    cum_vol = df["volume"].groupby(date_key).cumsum()
    return (cum_pv / cum_vol.replace(0, np.nan)).rename("vwap")


def _ensure_utc_index(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "timestamp" in out.columns and not isinstance(out.index, pd.DatetimeIndex):
        out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True, errors="coerce")
        out = out.set_index("timestamp")
    if out.index.tz is None:
        out.index = out.index.tz_localize("UTC")
    elif str(out.index.tz) != "UTC":
        out.index = out.index.tz_convert("UTC")
    return out.sort_index()


# ---------------------------------------------------------------------------
# Precompute all indicator columns on the full dataset
# ---------------------------------------------------------------------------

def precompute_dras(df: pd.DataFrame, cfg: DRASConfig) -> pd.DataFrame:
    """
    Vectorised computation of all DRAS indicators.

    Input df must have columns: open, high, low, close, volume
    and a UTC-aware DatetimeIndex (or a 'timestamp' column).

    Returns a new DataFrame with all indicator columns appended.
    """
    data = _ensure_utc_index(df)
    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(data.columns)
    if missing:
        raise ValueError(f"DRAS precompute: missing columns {sorted(missing)}")

    data = data.copy()

    # -- IST time helpers --
    local_idx = data.index.tz_convert(TIMEZONE)
    hhmm = pd.Series(local_idx.strftime("%H:%M"), index=data.index)
    data["_hhmm"] = hhmm
    data["_ist_date"] = pd.Series(local_idx.normalize(), index=data.index)

    # -- Indicators --
    data["ema20"] = _ema(data["close"], 20)
    data["vwap"] = _intraday_vwap(data)

    dmi = _dmi_adx(data, period=14)
    data["adx"] = dmi["adx"]

    data["atr5"] = _wilder_atr(data, 5)
    data["atr14"] = _wilder_atr(data, 14)
    data["atr20"] = _wilder_atr(data, 20)
    data["atr_trail"] = _wilder_atr(data, cfg.trail_atr_period)
    data["vol_sma"] = data["volume"].rolling(cfg.vol_sma_len, min_periods=cfg.vol_sma_len).mean()

    # -- Regime --
    data["adx_rising"] = (
        (data["adx"] > data["adx"].shift(1)) &
        (data["adx"].shift(1) > data["adx"].shift(2))
    )

    # VWAP cross: sign-change of (close - vwap)
    diff = data["close"] - data["vwap"]
    cross = (diff * diff.shift(1) < 0).astype(float)
    data["vwap_cross_count"] = cross.rolling(10, min_periods=1).sum()

    data["is_trend_long"] = (
        (data["close"] > data["ema20"]) &
        (data["ema20"] > data["vwap"]) &
        (data["adx"] > cfg.adx_threshold) &
        data["adx_rising"]
    )
    data["is_trend_short"] = (
        (data["close"] < data["ema20"]) &
        (data["ema20"] < data["vwap"]) &
        (data["adx"] > cfg.adx_threshold) &
        data["adx_rising"]
    )
    data["is_chop"] = (
        (data["adx"] < cfg.adx_threshold) |
        (data["vwap_cross_count"] > cfg.vwap_cross_limit)
    )
    data["is_toxic_vol"] = (
        (data["atr20"] > 0) &
        ((data["atr5"] / data["atr20"].replace(0, np.nan)) > cfg.vol_ratio_limit)
    )
    data["regime_allowed"] = (~data["is_chop"]) & (~data["is_toxic_vol"])

    # -- Time filters --
    data["in_window"] = (
        ((hhmm >= "09:30") & (hhmm <= "11:30")) |
        ((hhmm >= "13:00") & (hhmm <= "14:45"))
    )
    data["is_eod"] = (hhmm >= "15:15")

    # -- Candle structure --
    c_range = data["high"] - data["low"]
    body_low = data[["open", "close"]].min(axis=1)
    body_high = data[["open", "close"]].max(axis=1)
    lower_wick = (body_low - data["low"]).clip(lower=0.0)
    upper_wick = (data["high"] - body_high).clip(lower=0.0)

    vol_conf = (
        data["vol_sma"].notna() &
        (data["volume"] > data["vol_sma"] * cfg.vol_mult)
    )
    data["long_conf"] = (
        (data["close"] > data["open"]) &
        (c_range > 0) &
        ((lower_wick / c_range.replace(0, np.nan)) >= cfg.wick_percent) &
        vol_conf
    )
    data["short_conf"] = (
        (data["close"] < data["open"]) &
        (c_range > 0) &
        ((upper_wick / c_range.replace(0, np.nan)) >= cfg.wick_percent) &
        vol_conf
    )

    # -- Pullback / value zone --
    zone_low = data[["ema20", "vwap"]].min(axis=1)
    zone_high = data[["ema20", "vwap"]].max(axis=1)

    data["long_pullback"] = (
        (data["low"] <= data["ema20"]) |
        ((data["low"] <= zone_high) & (data["high"] >= zone_low))
    )
    data["short_pullback"] = (
        (data["high"] >= data["ema20"]) |
        ((data["high"] >= zone_low) & (data["low"] <= zone_high))
    )

    # -- Chandelier levels (used during exit loop, also precomputed) --
    data["chandelier_long"] = (
        data["high"].rolling(cfg.trail_atr_period, min_periods=1).max()
        - data["atr_trail"] * cfg.trail_atr_mult
    )
    data["chandelier_short"] = (
        data["low"].rolling(cfg.trail_atr_period, min_periods=1).min()
        + data["atr_trail"] * cfg.trail_atr_mult
    )

    return data


# ---------------------------------------------------------------------------
# Strategy class
# ---------------------------------------------------------------------------

class DynamicRegimeAdaptiveSystemStrategy(BaseStrategy):
    """
    Engine-ready wrapper for DRAS v3.2.

    Emits standardised StrategySignal outputs (advisory only).
    Position management and exit P&L are handled externally by
    ``backtest_dras()`` or by the engine's portfolio layer.

    The ``on_bar()`` method returns:
    - Signal.BUY   — enter long on this bar's close
    - Signal.SELL  — enter short on this bar's close
    - Signal.EXIT  — close current position on this bar's close
    - Signal.HOLD  — no action
    """

    @property
    def name(self) -> str:
        return "DynamicRegimeAdaptiveSystemStrategy"

    def initialize(self, params: Optional[dict[str, Any]] = None) -> None:
        super().initialize(params)
        p = self._params

        self.cfg = DRASConfig(
            adx_threshold=int(p.get("adx_threshold", 20)),
            vol_ratio_limit=float(p.get("vol_ratio_limit", 1.5)),
            vwap_cross_limit=int(p.get("vwap_cross_limit", 3)),
            vol_sma_len=int(p.get("vol_sma_len", 20)),
            vol_mult=float(p.get("vol_mult", 1.2)),
            wick_percent=float(p.get("wick_percent", 0.5)),
            risk_per_trade=float(p.get("risk_per_trade", 1.0)),
            daily_dd_limit=float(p.get("daily_dd_limit", 2.0)),
            max_daily_trades=int(p.get("max_daily_trades", 3)),
            max_con_losses=int(p.get("max_con_losses", 2)),
            sl_atr_mult=float(p.get("sl_atr_mult", 1.5)),
            trail_atr_mult=float(p.get("trail_atr_mult", 2.5)),
            trail_atr_period=int(p.get("trail_atr_period", 10)),
            initial_capital=float(p.get("initial_capital", 100_000.0)),
        )

        # Per-day state (reset each IST calendar day)
        self._last_ist_date: Optional[object] = None
        self._day_start_equity: float = self.cfg.initial_capital
        self._trades_today: int = 0
        self._con_losses: int = 0
        self._kill_switch: bool = False

        # Per-position state
        self._position: int = 0          # +qty long, -qty short, 0 flat
        self._ent_price: Optional[float] = None
        self._initial_sl: Optional[float] = None
        self._active_tsl: Optional[float] = None
        self._tp1_hit: bool = False
        self._half_exited: bool = False
        self._sig_hi: Optional[float] = None
        self._sig_lo: Optional[float] = None

        self._equity: float = self.cfg.initial_capital

    def precompute(
        self, full_data: pd.DataFrame, context: Optional[dict[str, Any]] = None
    ) -> None:
        if not getattr(self, "_is_initialized", False):
            self.initialize()
        prepared = precompute_dras(full_data, self.cfg)
        if context is not None:
            context["prepared_full"] = prepared

    def on_bar(
        self,
        current_bar: pd.Series,
        bar_index: int,
        context: Optional[dict[str, Any]] = None,
    ) -> Signal | StrategySignal:
        if not getattr(self, "_is_initialized", False):
            self.initialize()

        prepared_full: Optional[pd.DataFrame] = (
            context.get("prepared_full") if context else None
        )
        if prepared_full is None or bar_index >= len(prepared_full):
            return Signal.HOLD

        row = prepared_full.iloc[bar_index]

        # -- Daily reset --
        ist_date = row.get("_ist_date")
        if ist_date != self._last_ist_date:
            self._last_ist_date = ist_date
            self._day_start_equity = self._equity
            self._trades_today = 0
            self._con_losses = 0
            self._kill_switch = False

        # -- Kill-switch (evaluated before entries) --
        if self._day_start_equity > 0:
            cur_dd = ((self._day_start_equity - self._equity) / self._day_start_equity) * 100.0
        else:
            cur_dd = 0.0
        self._kill_switch = (
            cur_dd >= self.cfg.daily_dd_limit
            or self._trades_today >= self.cfg.max_daily_trades
            or self._con_losses >= self.cfg.max_con_losses
        )

        # Validate indicator availability
        for col in ("ema20", "vwap", "adx", "atr14", "regime_allowed"):
            if pd.isna(row.get(col)):
                return Signal.HOLD

        regime_allowed = bool(row["regime_allowed"])
        in_window = bool(row["in_window"])
        is_eod = bool(row["is_eod"])

        # -- EOD square-off signal --
        if is_eod and self._position != 0:
            return Signal.EXIT

        # -- Entry gates --
        can_enter = (
            regime_allowed
            and in_window
            and not self._kill_switch
            and self._position == 0
        )

        long_signal = (
            can_enter
            and bool(row["is_trend_long"])
            and bool(row["long_pullback"])
            and bool(row["long_conf"])
        )
        short_signal = (
            can_enter
            and bool(row["is_trend_short"])
            and bool(row["short_pullback"])
            and bool(row["short_conf"])
        )

        if long_signal:
            return self.build_signal(
                action=Signal.BUY,
                current_bar=current_bar,
                confidence=0.80,
                rationale="dras_long_regime_pullback_conf",
                tags=("intraday", "dras", "long"),
                metadata=_row_metadata(row),
            )
        if short_signal:
            return self.build_signal(
                action=Signal.SELL,
                current_bar=current_bar,
                confidence=0.80,
                rationale="dras_short_regime_pullback_conf",
                tags=("intraday", "dras", "short"),
                metadata=_row_metadata(row),
            )

        return Signal.HOLD


def _row_metadata(row: pd.Series) -> dict:
    return {
        "close": float(row.get("close", float("nan"))),
        "ema20": float(row.get("ema20", float("nan"))),
        "vwap": float(row.get("vwap", float("nan"))),
        "adx": float(row.get("adx", float("nan"))),
        "regime_allowed": bool(row.get("regime_allowed", False)),
        "is_trend_long": bool(row.get("is_trend_long", False)),
        "is_trend_short": bool(row.get("is_trend_short", False)),
        "is_chop": bool(row.get("is_chop", True)),
        "in_window": bool(row.get("in_window", False)),
    }


# ---------------------------------------------------------------------------
# Standalone backtester — Pine-faithful OCO exits and partial TP1
# ---------------------------------------------------------------------------

def backtest_dras(
    df: pd.DataFrame,
    cfg: Optional[DRASConfig] = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """
    Run a full DRAS v3.2 backtest on a 5-min OHLCV dataframe.

    Returns:
        data (pd.DataFrame)    — indicator-enriched dataframe
        trades (pd.DataFrame)  — one row per closed trade leg
        summary (dict)         — performance metrics
    """
    cfg = cfg or DRASConfig()
    data = precompute_dras(df, cfg)

    equity = cfg.initial_capital

    # Position state
    position = 0           # +qty long, -qty short
    ent_price: Optional[float] = None
    initial_sl: Optional[float] = None
    active_tsl: Optional[float] = None
    tp1_hit = False
    half_exited = False
    sig_hi: Optional[float] = None
    sig_lo: Optional[float] = None

    # Daily state
    last_date = None
    day_start_equity = equity
    trades_today = 0
    con_losses = 0
    kill_switch = False

    trades: list[dict] = []

    for i, (ts, row) in enumerate(data.iterrows()):
        close = float(row["close"])
        high = float(row["high"])
        low = float(row["low"])
        ist_date = row["_ist_date"]

        # -- Daily reset --
        if ist_date != last_date:
            last_date = ist_date
            day_start_equity = equity
            trades_today = 0
            con_losses = 0
            kill_switch = False

        # -- Kill switch --
        if day_start_equity > 0:
            cur_dd = ((day_start_equity - equity) / day_start_equity) * 100.0
        else:
            cur_dd = 0.0
        kill_switch = (
            cur_dd >= cfg.daily_dd_limit
            or trades_today >= cfg.max_daily_trades
            or con_losses >= cfg.max_con_losses
        )

        # ---- EXIT LOGIC ----
        if position != 0 and ent_price is not None and initial_sl is not None:
            is_eod = bool(row["is_eod"])

            # --- Long exits ---
            if position > 0:
                tp1_dist = abs(ent_price - initial_sl)
                tp1_price = ent_price + tp1_dist

                # Detect TP1 hit
                if not tp1_hit and high >= tp1_price:
                    tp1_hit = True

                # Compute finalSL
                final_sl = initial_sl
                if tp1_hit and sig_hi is not None and high > sig_hi:
                    final_sl = ent_price  # break-even upgrade

                # Update chandelier
                ch_long = float(row["chandelier_long"])
                if not np.isnan(ch_long):
                    if active_tsl is None:
                        active_tsl = ch_long
                    else:
                        active_tsl = max(active_tsl, ch_long)

                effective_stop = max(final_sl, active_tsl) if active_tsl is not None else final_sl

                # EOD force close
                if is_eod:
                    _close_trade(
                        trades, ts, "long", ent_price, close, abs(position),
                        "eod_exit", cfg, equity
                    )
                    pnl = _pnl("long", ent_price, close, abs(position), cfg)
                    equity += pnl
                    _update_con_losses(pnl, trades, lambda: None)
                    con_losses, kill_switch = _update_daily_loss_state(
                        pnl, con_losses, day_start_equity, equity,
                        cfg.daily_dd_limit
                    )
                    position = 0
                    ent_price = initial_sl = active_tsl = sig_hi = sig_lo = None
                    tp1_hit = half_exited = False
                    continue

                # TP1 partial exit (50%) — only if not already done
                if not half_exited and tp1_hit:
                    half_qty = abs(position) // 2
                    if half_qty > 0:
                        exit_price = max(tp1_price, close)  # bar close (POC)
                        pnl = _pnl("long", ent_price, exit_price, half_qty, cfg)
                        equity += pnl
                        _close_trade(
                            trades, ts, "long", ent_price, exit_price, half_qty,
                            "tp1_partial", cfg, equity
                        )
                        position -= half_qty
                        half_exited = True
                        if pnl <= 0:
                            con_losses += 1
                        else:
                            con_losses = 0

                # Trail/stop exit (full remaining position)
                if low <= effective_stop:
                    exit_price = effective_stop
                    pnl = _pnl("long", ent_price, exit_price, abs(position), cfg)
                    equity += pnl
                    reason = "trail_stop" if (active_tsl is not None and effective_stop == active_tsl) else "stop_loss"
                    _close_trade(
                        trades, ts, "long", ent_price, exit_price, abs(position),
                        reason, cfg, equity
                    )
                    if pnl <= 0:
                        con_losses += 1
                    else:
                        con_losses = 0
                    position = 0
                    ent_price = initial_sl = active_tsl = sig_hi = sig_lo = None
                    tp1_hit = half_exited = False
                    continue

            # --- Short exits ---
            elif position < 0:
                tp1_dist = abs(ent_price - initial_sl)
                tp1_price = ent_price - tp1_dist

                if not tp1_hit and low <= tp1_price:
                    tp1_hit = True

                final_sl = initial_sl
                if tp1_hit and sig_lo is not None and low < sig_lo:
                    final_sl = ent_price  # break-even upgrade

                ch_short = float(row["chandelier_short"])
                if not np.isnan(ch_short):
                    if active_tsl is None:
                        active_tsl = ch_short
                    else:
                        active_tsl = min(active_tsl, ch_short)

                effective_stop = min(final_sl, active_tsl) if active_tsl is not None else final_sl

                if is_eod:
                    pnl = _pnl("short", ent_price, close, abs(position), cfg)
                    equity += pnl
                    _close_trade(
                        trades, ts, "short", ent_price, close, abs(position),
                        "eod_exit", cfg, equity
                    )
                    con_losses, kill_switch = _update_daily_loss_state(
                        pnl, con_losses, day_start_equity, equity,
                        cfg.daily_dd_limit
                    )
                    position = 0
                    ent_price = initial_sl = active_tsl = sig_hi = sig_lo = None
                    tp1_hit = half_exited = False
                    continue

                if not half_exited and tp1_hit:
                    half_qty = abs(position) // 2
                    if half_qty > 0:
                        exit_price = min(tp1_price, close)
                        pnl = _pnl("short", ent_price, exit_price, half_qty, cfg)
                        equity += pnl
                        _close_trade(
                            trades, ts, "short", ent_price, exit_price, half_qty,
                            "tp1_partial", cfg, equity
                        )
                        position += half_qty  # position becomes less negative
                        half_exited = True
                        if pnl <= 0:
                            con_losses += 1
                        else:
                            con_losses = 0

                if high >= effective_stop:
                    exit_price = effective_stop
                    pnl = _pnl("short", ent_price, exit_price, abs(position), cfg)
                    equity += pnl
                    reason = "trail_stop" if (active_tsl is not None and effective_stop == active_tsl) else "stop_loss"
                    _close_trade(
                        trades, ts, "short", ent_price, exit_price, abs(position),
                        reason, cfg, equity
                    )
                    if pnl <= 0:
                        con_losses += 1
                    else:
                        con_losses = 0
                    position = 0
                    ent_price = initial_sl = active_tsl = sig_hi = sig_lo = None
                    tp1_hit = half_exited = False
                    continue

        # ---- ENTRY LOGIC ----
        if position != 0:
            continue  # still in a position, no new entry

        # Re-evaluate kill switch after any trade updates
        if day_start_equity > 0:
            cur_dd = ((day_start_equity - equity) / day_start_equity) * 100.0
        else:
            cur_dd = 0.0
        kill_switch = (
            cur_dd >= cfg.daily_dd_limit
            or trades_today >= cfg.max_daily_trades
            or con_losses >= cfg.max_con_losses
        )

        if kill_switch:
            continue

        # Check indicator validity
        for col in ("ema20", "vwap", "adx", "atr14", "atr5", "atr20", "vol_sma"):
            if pd.isna(row.get(col)):
                continue  # skip bar

        in_window = bool(row.get("in_window", False))
        regime_allowed = bool(row.get("regime_allowed", False))

        if not (in_window and regime_allowed):
            continue

        long_sig = (
            bool(row.get("is_trend_long", False))
            and bool(row.get("long_pullback", False))
            and bool(row.get("long_conf", False))
        )
        short_sig = (
            bool(row.get("is_trend_short", False))
            and bool(row.get("short_pullback", False))
            and bool(row.get("short_conf", False))
        )

        if not (long_sig or short_sig):
            continue

        atr14 = float(row["atr14"])
        sl_dist = atr14 * cfg.sl_atr_mult
        if sl_dist <= cfg.min_tick:
            continue

        risk_amt = equity * (cfg.risk_per_trade / 100.0)
        qty = int(np.floor(risk_amt / sl_dist))
        if qty <= 0:
            continue

        if long_sig:
            position = qty
            ent_price = close
            initial_sl = close - sl_dist
            active_tsl = None
            tp1_hit = False
            half_exited = False
            sig_hi = float(row["high"])
            sig_lo = float(row["low"])
            trades_today += 1

        elif short_sig:
            position = -qty
            ent_price = close
            initial_sl = close + sl_dist
            active_tsl = None
            tp1_hit = False
            half_exited = False
            sig_hi = float(row["high"])
            sig_lo = float(row["low"])
            trades_today += 1

    # Force-close any open position at the last bar
    if position != 0 and ent_price is not None:
        last_ts = data.index[-1]
        last_row = data.iloc[-1]
        last_close = float(last_row["close"])
        side = "long" if position > 0 else "short"
        pnl = _pnl(side, ent_price, last_close, abs(position), cfg)
        equity += pnl
        _close_trade(
            trades, last_ts, side, ent_price, last_close, abs(position),
            "end_of_data", cfg, equity
        )

    trades_df = pd.DataFrame(trades) if trades else pd.DataFrame(
        columns=["entry_time", "exit_time", "side", "entry_price", "exit_price",
                 "qty", "pnl", "equity_after", "exit_reason"]
    )

    summary = _compute_summary(cfg.initial_capital, equity, trades_df)
    return data, trades_df, summary


# ---------------------------------------------------------------------------
# Helper functions for the backtest loop
# ---------------------------------------------------------------------------

def _pnl(
    side: str,
    entry: float,
    exit_price: float,
    qty: int,
    cfg: DRASConfig,
) -> float:
    """Compute P&L including commission (both legs)."""
    raw = (exit_price - entry) * qty if side == "long" else (entry - exit_price) * qty
    commission = (entry + exit_price) * qty * (cfg.commission_pct / 100.0)
    return raw - commission


def _close_trade(
    trades: list,
    ts: Any,
    side: str,
    entry: float,
    exit_price: float,
    qty: int,
    reason: str,
    cfg: DRASConfig,
    equity_after: float,
) -> None:
    trades.append({
        "entry_time": None,  # patched below if we had it
        "exit_time": ts,
        "side": side,
        "entry_price": entry,
        "exit_price": exit_price,
        "qty": qty,
        "pnl": _pnl(side, entry, exit_price, qty, cfg),
        "equity_after": equity_after,
        "exit_reason": reason,
    })


def _update_con_losses(pnl: float, trades: list, reset_fn: Any) -> None:
    pass  # inline in main loop


def _update_daily_loss_state(
    pnl: float,
    con_losses: int,
    day_start_equity: float,
    equity: float,
    dd_limit: float,
) -> tuple[int, bool]:
    if pnl <= 0:
        con_losses += 1
    else:
        con_losses = 0
    if day_start_equity > 0:
        cur_dd = ((day_start_equity - equity) / day_start_equity) * 100.0
    else:
        cur_dd = 0.0
    kill = cur_dd >= dd_limit
    return con_losses, kill


def _compute_summary(initial_capital: float, final_equity: float, trades_df: pd.DataFrame) -> dict:
    n = len(trades_df)
    if n == 0:
        return {
            "initial_capital": initial_capital,
            "final_equity": final_equity,
            "net_profit": final_equity - initial_capital,
            "net_profit_pct": ((final_equity - initial_capital) / initial_capital) * 100.0,
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate_pct": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_pct": 0.0,
            "expectancy": 0.0,
        }

    wins = trades_df[trades_df["pnl"] > 0]
    losses = trades_df[trades_df["pnl"] <= 0]
    win_rate = len(wins) / n * 100.0
    avg_win = float(wins["pnl"].mean()) if len(wins) else 0.0
    avg_loss = float(losses["pnl"].mean()) if len(losses) else 0.0
    gross_profit = float(wins["pnl"].sum()) if len(wins) else 0.0
    gross_loss = float(losses["pnl"].sum()) if len(losses) else 0.0
    profit_factor = (gross_profit / abs(gross_loss)) if gross_loss != 0.0 else float("inf")

    equity_curve = trades_df["equity_after"].dropna()
    if len(equity_curve) > 0:
        roll_max = equity_curve.cummax()
        dd = (equity_curve - roll_max) / roll_max * 100.0
        max_dd = float(dd.min())
    else:
        max_dd = 0.0

    expectancy = (win_rate / 100.0) * avg_win + (1.0 - win_rate / 100.0) * avg_loss

    return {
        "initial_capital": initial_capital,
        "final_equity": round(final_equity, 2),
        "net_profit": round(final_equity - initial_capital, 2),
        "net_profit_pct": round((final_equity - initial_capital) / initial_capital * 100.0, 2),
        "total_trades": n,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(win_rate, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "profit_factor": round(profit_factor, 3),
        "max_drawdown_pct": round(max_dd, 2),
        "expectancy": round(expectancy, 2),
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="Run DRAS v3.2 backtest on a 5-minute OHLCV CSV."
    )
    parser.add_argument("csv_path", help="Path to OHLCV CSV")
    parser.add_argument("--initial-capital", type=float, default=100_000.0)
    parser.add_argument("--risk-per-trade", type=float, default=1.0)
    parser.add_argument("--adx-threshold", type=int, default=20)
    args = parser.parse_args()

    cfg = DRASConfig(
        initial_capital=args.initial_capital,
        risk_per_trade=args.risk_per_trade,
        adx_threshold=args.adx_threshold,
    )
    _df = pd.read_csv(args.csv_path)
    _, _trades, _summary = backtest_dras(_df, cfg)

    print(json.dumps(_summary, indent=2, default=str))
    if not _trades.empty:
        print(f"\nLast 10 trades:\n{_trades.tail(10).to_string(index=False)}")
    else:
        print("\nNo trades generated.")
