from __future__ import annotations

import pandas as pd

from src.monitoring.config import SnapshotConfig
from src.monitoring.models import (
    RegimeAssessment,
    RegimeState,
    RelativeStrengthSnapshot,
    Watchlist,
    WatchlistItem,
)
from src.monitoring.snapshot_engine import SnapshotEngine
from src.scanners.models import Opportunity, OpportunityClass, ScanResult


def _opportunity(symbol: str, score: float) -> Opportunity:
    return Opportunity(
        symbol=symbol,
        timeframe="1D",
        strategy_name="RSIReversionStrategy",
        signal="buy",
        timestamp=pd.Timestamp("2026-03-07 09:15:00", tz="UTC"),
        classification=OpportunityClass.POSITIONAL,
        entry_price=100.0,
        stop_loss=95.0,
        target_price=110.0,
        score=score,
        reasons=["actionable_buy_signal"],
    )


def test_snapshot_top_n_and_min_score() -> None:
    result = ScanResult(opportunities=[_opportunity("A.NS", 82), _opportunity("B.NS", 65)])
    cfg = SnapshotConfig(top_n=1, min_score=70.0)

    snapshot = SnapshotEngine().build_snapshot(scan_result=result, config=cfg)
    assert len(snapshot.top_picks) == 1
    assert snapshot.top_picks[0].symbol == "A.NS"


def test_snapshot_includes_regime_rs_and_watchlist_context() -> None:
    result = ScanResult(opportunities=[_opportunity("RELIANCE.NS", 88)])
    cfg = SnapshotConfig(top_n=5, min_score=0)
    regime = RegimeAssessment(regime=RegimeState.BULLISH)
    rs = [RelativeStrengthSnapshot(symbol="RELIANCE.NS", score=0.77, rank=2)]
    watchlists = {
        "swing": Watchlist(
            name="swing",
            items=[WatchlistItem(symbol="RELIANCE.NS", tags=["high_conviction"])],
        )
    }

    snapshot = SnapshotEngine().build_snapshot(
        scan_result=result,
        config=cfg,
        regime_assessment=regime,
        relative_strength=rs,
        watchlists=watchlists,
    )

    assert len(snapshot.top_picks) == 1
    pick = snapshot.top_picks[0]
    assert pick.regime_context == "bullish"
    assert pick.relative_strength_score == 0.77
    assert "high_conviction" in pick.watchlist_tags
    assert "swing" in pick.watchlist_tags
