from __future__ import annotations

import pandas as pd
import pytest

from src.scanners.models import (
    Opportunity,
    OpportunityClass,
    OpportunitySide,
    ScanResult,
    SignalSnapshot,
    TradeSetup,
)


def test_signal_snapshot_actionable_buy() -> None:
    snap = SignalSnapshot(
        symbol="RELIANCE.NS",
        timeframe="15m",
        strategy_name="SMACrossoverStrategy",
        signal="BUY",
        timestamp=pd.Timestamp("2026-01-05 10:15:00"),
        close_price=2500.0,
    )
    assert snap.signal == "buy"
    assert snap.is_actionable is True


def test_signal_snapshot_non_actionable_hold() -> None:
    snap = SignalSnapshot(
        symbol="RELIANCE.NS",
        timeframe="15m",
        strategy_name="SMACrossoverStrategy",
        signal="hold",
        timestamp=pd.Timestamp("2026-01-05 10:15:00"),
        close_price=2500.0,
    )
    assert snap.is_actionable is False


def test_trade_setup_risk_reward_ratio_long() -> None:
    setup = TradeSetup(
        entry_price=100.0,
        stop_loss=95.0,
        target_price=110.0,
        side=OpportunitySide.LONG,
    )
    assert setup.risk_per_unit == pytest.approx(5.0)
    assert setup.reward_per_unit == pytest.approx(10.0)
    assert setup.risk_reward_ratio == pytest.approx(2.0)


def test_trade_setup_invalid_long_prices_raise() -> None:
    with pytest.raises(ValueError):
        TradeSetup(entry_price=100.0, stop_loss=101.0, target_price=110.0)


def test_opportunity_from_parts() -> None:
    snap = SignalSnapshot(
        symbol="TCS.NS",
        timeframe="1h",
        strategy_name="BreakoutStrategy",
        signal="buy",
        timestamp=pd.Timestamp("2026-01-05 12:30:00"),
        close_price=4050.0,
    )
    setup = TradeSetup(entry_price=4050.0, stop_loss=3980.0, target_price=4190.0)

    opp = Opportunity.from_parts(
        snapshot=snap,
        setup=setup,
        classification=OpportunityClass.SWING,
        score=78.5,
        reasons=["breakout_confirmed"],
        score_components={"signal": 0.7, "risk_reward": 0.8, "trend": 0.5, "liquidity": 0.6, "freshness": 0.9},
    )

    assert opp.symbol == "TCS.NS"
    assert opp.classification == OpportunityClass.SWING
    assert opp.score == pytest.approx(78.5)
    d = opp.to_dict()
    assert "score_signal" in d
    assert "score_rr" in d


def test_scan_result_top_and_dataframe() -> None:
    ts = pd.Timestamp("2026-01-05 12:30:00")
    opp1 = Opportunity(
        symbol="A.NS",
        timeframe="1D",
        strategy_name="S1",
        signal="buy",
        timestamp=ts,
        classification=OpportunityClass.POSITIONAL,
        entry_price=100,
        stop_loss=95,
        target_price=110,
        score=80,
    )
    opp2 = Opportunity(
        symbol="B.NS",
        timeframe="1D",
        strategy_name="S1",
        signal="buy",
        timestamp=ts,
        classification=OpportunityClass.POSITIONAL,
        entry_price=200,
        stop_loss=190,
        target_price=225,
        score=90,
    )

    result = ScanResult(opportunities=[opp1, opp2])
    top = result.get_top(1)

    assert len(top) == 1
    assert top[0].symbol == "B.NS"
    assert top[0].rank == 1

    df = result.to_dataframe(top_n=1)
    assert len(df) == 1
    assert df.iloc[0]["symbol"] == "B.NS"
