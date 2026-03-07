from __future__ import annotations

import pandas as pd
import pytest

from src.monitoring.models import (
    Alert,
    AlertSeverity,
    MarketSnapshot,
    MonitoringRunResult,
    RegimeAssessment,
    RegimeState,
    ScheduleMode,
    ScheduleSpec,
    TopPick,
    Watchlist,
    WatchlistItem,
)
from src.scanners.models import ScanResult


def test_watchlist_item_normalizes_symbol_tags_and_timeframes() -> None:
    item = WatchlistItem(
        symbol=" reliance.ns ",
        tags=[" Swing ", "swing", "HighConviction"],
        default_timeframes=["1d", "1D", "60m"],
    )
    assert item.symbol == "RELIANCE.NS"
    assert item.tags == ["swing", "highconviction"]
    assert item.default_timeframes == ["1D", "1h"]


def test_watchlist_symbols_are_deduped_in_order() -> None:
    watchlist = Watchlist(
        name="nifty swing",
        items=[
            WatchlistItem(symbol="RELIANCE.NS"),
            WatchlistItem(symbol="TCS.NS"),
            WatchlistItem(symbol="RELIANCE.NS"),
        ],
    )
    assert watchlist.symbols == ["RELIANCE.NS", "TCS.NS"]


def test_regime_assessment_to_dict_shape() -> None:
    assessment = RegimeAssessment(
        regime=RegimeState.BULLISH,
        trend_score=0.8,
        volatility_score=0.2,
        reason="fast_ma_above_slow_ma",
    )
    payload = assessment.to_dict()
    assert payload["regime"] == "bullish"
    assert payload["trend_score"] == pytest.approx(0.8)
    assert "timestamp" in payload


def test_alert_auto_builds_dedupe_key() -> None:
    alert = Alert(
        rule_id="opportunity_score_cross",
        symbol="reliance.ns",
        title="Score crossed threshold",
        message="Opportunity score moved above 80",
        severity=AlertSeverity.WARNING,
    )
    assert alert.symbol == "RELIANCE.NS"
    assert alert.dedupe_key == "opportunity_score_cross|RELIANCE.NS|score crossed threshold"


def test_top_pick_to_dict_has_expected_fields() -> None:
    ts = pd.Timestamp("2026-03-06 09:15:00", tz="UTC")
    pick = TopPick(
        symbol="tcs.ns",
        timeframe="1d",
        strategy_name="SMACrossoverStrategy",
        timestamp=ts,
        entry_price=4050.0,
        stop_loss=3980.0,
        target_price=4190.0,
        score=82.5,
        horizon="positional",
        regime_context="bullish",
        relative_strength_score=0.78,
        watchlist_tags=["swing"],
        reasons=["trend_aligned", "high_score"],
    )
    payload = pick.to_dict()
    assert payload["symbol"] == "TCS.NS"
    assert payload["timeframe"] == "1D"
    assert payload["score"] == pytest.approx(82.5)
    assert payload["horizon"] == "positional"


def test_schedule_spec_validation_for_interval_and_daily() -> None:
    with pytest.raises(ValueError):
        ScheduleSpec(name="bad_interval", mode=ScheduleMode.INTERVAL, interval_minutes=0)

    with pytest.raises(ValueError):
        ScheduleSpec(name="bad_daily", mode=ScheduleMode.DAILY, daily_time=None)

    good = ScheduleSpec(name="ok", mode=ScheduleMode.INTERVAL, interval_minutes=15)
    assert good.mode == ScheduleMode.INTERVAL


def test_monitoring_run_result_to_dict_summary() -> None:
    snapshot = MarketSnapshot()
    result = MonitoringRunResult(scan_result=ScanResult(), snapshot=snapshot)
    payload = result.to_dict()

    assert "generated_at" in payload
    assert payload["scan"]["total_opportunities"] == 0
    assert payload["snapshot"]["top_picks"] == []
