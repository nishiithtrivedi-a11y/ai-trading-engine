from __future__ import annotations

import pandas as pd
import pytest

from src.core.data_handler import DataHandler
from src.scanners.config import ScannerConfig
from src.scanners.models import Opportunity, OpportunityClass, SignalSnapshot, TradeSetup
from src.scanners.scorer import OpportunityScorer


def _build_data(num_bars: int = 80) -> DataHandler:
    df = pd.DataFrame(
        {
            "open": [100 + i * 0.4 for i in range(num_bars)],
            "high": [101 + i * 0.4 for i in range(num_bars)],
            "low": [99 + i * 0.4 for i in range(num_bars)],
            "close": [100.5 + i * 0.45 for i in range(num_bars)],
            "volume": [1000 + (i % 10) * 50 for i in range(num_bars)],
        },
        index=pd.date_range("2026-01-01", periods=num_bars, freq="D", name="timestamp"),
    )
    return DataHandler(df)


def _buy_signal(ts: pd.Timestamp) -> SignalSnapshot:
    return SignalSnapshot(
        symbol="RELIANCE.NS",
        timeframe="1D",
        strategy_name="Dummy",
        signal="buy",
        timestamp=ts,
        close_price=200.0,
        extras={"confidence": 0.8},
    )


def test_score_range_bounds() -> None:
    dh = _build_data()
    scorer = OpportunityScorer()
    cfg = ScannerConfig()

    signal = _buy_signal(dh.data.index[-1])
    setup = TradeSetup(entry_price=200.0, stop_loss=195.0, target_price=210.0)

    result = scorer.score(signal, setup, dh, cfg)
    assert 0.0 <= result["score"] <= 100.0


def test_better_rr_gets_higher_score() -> None:
    dh = _build_data()
    scorer = OpportunityScorer()
    cfg = ScannerConfig(score_weights={"risk_reward": 1.0})
    signal = _buy_signal(dh.data.index[-1])

    low_rr = TradeSetup(entry_price=200.0, stop_loss=198.0, target_price=202.0)
    high_rr = TradeSetup(entry_price=200.0, stop_loss=198.0, target_price=206.0)

    s1 = scorer.score(signal, low_rr, dh, cfg)["score"]
    s2 = scorer.score(signal, high_rr, dh, cfg)["score"]

    assert s2 > s1


def test_freshness_uses_trigger_age() -> None:
    dh = _build_data()
    scorer = OpportunityScorer()
    cfg = ScannerConfig(score_weights={"freshness": 1.0})

    recent_signal = SignalSnapshot(
        symbol="RELIANCE.NS",
        timeframe="1D",
        strategy_name="Dummy",
        signal="buy",
        timestamp=dh.data.index[-1],
        close_price=200.0,
        extras={"bars_since_trigger": 0},
    )
    old_signal = SignalSnapshot(
        symbol="RELIANCE.NS",
        timeframe="1D",
        strategy_name="Dummy",
        signal="buy",
        timestamp=dh.data.index[-1],
        close_price=200.0,
        extras={"bars_since_trigger": 12},
    )
    setup = TradeSetup(entry_price=200.0, stop_loss=198.0, target_price=206.0)

    recent_score = scorer.score(recent_signal, setup, dh, cfg)["score"]
    old_score = scorer.score(old_signal, setup, dh, cfg)["score"]

    assert recent_score > old_score


def test_rsi_signal_strength_scales_with_distance_below_oversold() -> None:
    dh = _build_data()
    scorer = OpportunityScorer()
    cfg = ScannerConfig(score_weights={"signal": 1.0})
    setup = TradeSetup(entry_price=200.0, stop_loss=198.0, target_price=206.0)

    deep_oversold = SignalSnapshot(
        symbol="RELIANCE.NS",
        timeframe="1D",
        strategy_name="RSIReversionStrategy",
        signal="buy",
        timestamp=dh.data.index[-1],
        close_price=200.0,
        strategy_params={"oversold": 30, "rsi_period": 14},
        extras={"rsi_current": 20.0, "rsi_slope": 1.0},
    )
    shallow_oversold = SignalSnapshot(
        symbol="RELIANCE.NS",
        timeframe="1D",
        strategy_name="RSIReversionStrategy",
        signal="buy",
        timestamp=dh.data.index[-1],
        close_price=200.0,
        strategy_params={"oversold": 30, "rsi_period": 14},
        extras={"rsi_current": 29.0, "rsi_slope": 1.0},
    )

    s1 = scorer.score(deep_oversold, setup, dh, cfg)["score"]
    s2 = scorer.score(shallow_oversold, setup, dh, cfg)["score"]
    assert s1 > s2


def test_sma_signal_strength_scales_with_normalized_spread() -> None:
    dh = _build_data()
    scorer = OpportunityScorer()
    cfg = ScannerConfig(score_weights={"signal": 1.0})
    setup = TradeSetup(entry_price=200.0, stop_loss=198.0, target_price=206.0)

    strong = SignalSnapshot(
        symbol="RELIANCE.NS",
        timeframe="1D",
        strategy_name="SMACrossoverStrategy",
        signal="buy",
        timestamp=dh.data.index[-1],
        close_price=200.0,
        strategy_params={"fast_period": 10, "slow_period": 30},
        extras={"sma_spread_norm": 1.2},
    )
    weak = SignalSnapshot(
        symbol="RELIANCE.NS",
        timeframe="1D",
        strategy_name="SMACrossoverStrategy",
        signal="buy",
        timestamp=dh.data.index[-1],
        close_price=200.0,
        strategy_params={"fast_period": 10, "slow_period": 30},
        extras={"sma_spread_norm": 0.1},
    )

    s1 = scorer.score(strong, setup, dh, cfg)["score"]
    s2 = scorer.score(weak, setup, dh, cfg)["score"]
    assert s1 > s2


def test_rank_orders_descending() -> None:
    ts = pd.Timestamp("2026-03-01")
    opp1 = Opportunity(
        symbol="A.NS",
        timeframe="1D",
        strategy_name="S",
        signal="buy",
        timestamp=ts,
        classification=OpportunityClass.POSITIONAL,
        entry_price=100,
        stop_loss=95,
        target_price=110,
        score=50,
    )
    opp2 = Opportunity(
        symbol="B.NS",
        timeframe="1D",
        strategy_name="S",
        signal="buy",
        timestamp=ts,
        classification=OpportunityClass.POSITIONAL,
        entry_price=100,
        stop_loss=95,
        target_price=110,
        score=90,
    )

    ranked = OpportunityScorer.rank([opp1, opp2])
    assert ranked[0].symbol == "B.NS"
    assert ranked[0].rank == 1
    assert ranked[1].rank == 2


def test_missing_optional_signal_fields_handled() -> None:
    dh = _build_data()
    scorer = OpportunityScorer()
    cfg = ScannerConfig()

    signal = SignalSnapshot(
        symbol="RELIANCE.NS",
        timeframe="1D",
        strategy_name="Dummy",
        signal="buy",
        timestamp=dh.data.index[-1],
        close_price=200.0,
        extras={},
    )
    setup = TradeSetup(entry_price=200.0, stop_loss=198.0, target_price=206.0)

    result = scorer.score(signal, setup, dh, cfg)
    assert 0.0 <= result["signal"] <= 1.0
    assert 0.0 <= result["score"] <= 100.0
