from __future__ import annotations

import pandas as pd

from src.monitoring.config import AlertEngineConfig
from src.monitoring.alert_engine import AlertEngine
from src.monitoring.models import (
    RegimeAssessment,
    RegimeState,
    RelativeStrengthSnapshot,
    Watchlist,
    WatchlistItem,
)
from src.scanners.models import Opportunity, OpportunityClass, ScanResult


def _opportunity(score: float = 90.0) -> Opportunity:
    return Opportunity(
        symbol="RELIANCE.NS",
        timeframe="1D",
        strategy_name="SMACrossoverStrategy",
        signal="buy",
        timestamp=pd.Timestamp("2026-03-07 09:15:00", tz="UTC"),
        classification=OpportunityClass.POSITIONAL,
        entry_price=2500.0,
        stop_loss=2450.0,
        target_price=2600.0,
        score=score,
    )


def test_actionable_opportunity_alert_generated() -> None:
    engine = AlertEngine()
    cfg = AlertEngineConfig(min_opportunity_score=60, high_priority_score=85)
    result = ScanResult(opportunities=[_opportunity(90.0)])

    alerts = engine.generate(scan_result=result, config=cfg, now=pd.Timestamp("2026-03-07 10:00:00", tz="UTC"))
    assert len(alerts) == 1
    assert alerts[0].severity.value == "high_priority"
    assert alerts[0].symbol == "RELIANCE.NS"


def test_alert_deduplication_window() -> None:
    engine = AlertEngine()
    cfg = AlertEngineConfig(min_opportunity_score=60, dedupe_window_minutes=120)
    result = ScanResult(opportunities=[_opportunity(75.0)])
    t0 = pd.Timestamp("2026-03-07 10:00:00", tz="UTC")

    first = engine.generate(scan_result=result, config=cfg, now=t0)
    second = engine.generate(scan_result=result, config=cfg, now=t0 + pd.Timedelta(minutes=30))
    third = engine.generate(scan_result=result, config=cfg, now=t0 + pd.Timedelta(minutes=130))

    assert len(first) == 1
    assert len(second) == 0
    assert len(third) == 1


def test_regime_change_alert_generated() -> None:
    engine = AlertEngine()
    cfg = AlertEngineConfig(include_regime_change_alerts=True)
    regime = RegimeAssessment(regime=RegimeState.BEARISH)

    alerts = engine.generate(
        scan_result=None,
        config=cfg,
        regime_assessment=regime,
        previous_regime=RegimeState.BULLISH,
        now=pd.Timestamp("2026-03-07 10:00:00", tz="UTC"),
    )
    assert len(alerts) == 1
    assert alerts[0].rule_id == "regime_change"


def test_relative_strength_top_n_alerts() -> None:
    engine = AlertEngine()
    cfg = AlertEngineConfig(include_relative_strength_alerts=True, relative_strength_top_n=2)
    rs = [
        RelativeStrengthSnapshot(symbol="RELIANCE.NS", score=0.9, rank=1),
        RelativeStrengthSnapshot(symbol="TCS.NS", score=0.8, rank=3),
    ]

    alerts = engine.generate(
        scan_result=None,
        config=cfg,
        relative_strength=rs,
        now=pd.Timestamp("2026-03-07 10:00:00", tz="UTC"),
    )
    assert len(alerts) == 1
    assert alerts[0].symbol == "RELIANCE.NS"


def test_watchlist_filter_only_emits_for_watchlist_symbols() -> None:
    engine = AlertEngine()
    cfg = AlertEngineConfig(include_watchlist_actionable_alerts=True, min_opportunity_score=60)
    result = ScanResult(
        opportunities=[
            _opportunity(80),
            Opportunity(
                symbol="INFY.NS",
                timeframe="1D",
                strategy_name="SMACrossoverStrategy",
                signal="buy",
                timestamp=pd.Timestamp("2026-03-07 09:15:00", tz="UTC"),
                classification=OpportunityClass.POSITIONAL,
                entry_price=1500.0,
                stop_loss=1470.0,
                target_price=1560.0,
                score=80.0,
            ),
        ]
    )
    watchlists = {
        "swing": Watchlist(name="swing", items=[WatchlistItem(symbol="RELIANCE.NS")])
    }

    alerts = engine.generate(
        scan_result=result,
        config=cfg,
        watchlists=watchlists,
        now=pd.Timestamp("2026-03-07 10:00:00", tz="UTC"),
    )
    assert len(alerts) == 1
    assert alerts[0].symbol == "RELIANCE.NS"
