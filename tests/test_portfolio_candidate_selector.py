from __future__ import annotations

from src.decision.config import DecisionConfig, DecisionThresholdsConfig, SelectionPolicyConfig
from src.decision.models import ConvictionBreakdown, DecisionHorizon, RankedPick, TradePlan
from src.decision.portfolio_candidate_selector import PortfolioCandidateSelector


def _pick(
    symbol: str,
    horizon: DecisionHorizon,
    conviction: float,
    rr: float,
    sector: str | None = None,
    timeframe: str = "1D",
    strategy: str = "S1",
) -> RankedPick:
    plan = TradePlan(
        symbol=symbol,
        timeframe=timeframe,
        strategy_name=strategy,
        entry_price=100.0,
        stop_loss=99.0,
        target_price=100.0 + rr,
        risk_reward=rr,
        horizon=horizon,
        metadata={"sector": sector} if sector else {},
    )
    breakdown = ConvictionBreakdown(
        scanner_score=70.0,
        setup_quality=70.0,
        risk_reward=70.0,
        regime_compatibility=70.0,
        relative_strength=70.0,
        liquidity=70.0,
        freshness=70.0,
        final_score=conviction,
    )
    return RankedPick(
        trade_plan=plan,
        conviction_score=conviction,
        conviction_breakdown=breakdown,
        scanner_score=70.0,
    )


def test_selector_enforces_horizon_cap() -> None:
    cfg = DecisionConfig(
        thresholds=DecisionThresholdsConfig(
            max_picks_by_horizon={
                DecisionHorizon.INTRADAY: 1,
                DecisionHorizon.SWING: 5,
                DecisionHorizon.POSITIONAL: 5,
            }
        )
    )
    candidates = [
        _pick("A.NS", DecisionHorizon.INTRADAY, 90, 2.0),
        _pick("B.NS", DecisionHorizon.INTRADAY, 80, 2.0),
    ]

    selected, rejected = PortfolioCandidateSelector().select(candidates, cfg)
    assert len(selected) == 1
    assert selected[0].symbol == "A.NS"
    assert len(rejected) == 1
    assert rejected[0].rejection_reasons[0].value == "horizon_cap_reached"


def test_selector_enforces_sector_cap() -> None:
    cfg = DecisionConfig(
        thresholds=DecisionThresholdsConfig(max_picks_per_sector=1)
    )
    candidates = [
        _pick("A.NS", DecisionHorizon.SWING, 90, 2.0, sector="IT"),
        _pick("B.NS", DecisionHorizon.SWING, 89, 2.0, sector="IT"),
    ]
    selected, rejected = PortfolioCandidateSelector().select(candidates, cfg)

    assert len(selected) == 1
    assert len(rejected) == 1
    assert rejected[0].rejection_reasons[0].value == "sector_cap_reached"


def test_selector_enforces_unique_symbol() -> None:
    cfg = DecisionConfig(
        selection_policy=SelectionPolicyConfig(enforce_unique_symbol=True)
    )
    candidates = [
        _pick("RELIANCE.NS", DecisionHorizon.SWING, 90, 2.0, timeframe="1D"),
        _pick("RELIANCE.NS", DecisionHorizon.POSITIONAL, 88, 2.0, timeframe="1h"),
    ]
    selected, rejected = PortfolioCandidateSelector().select(candidates, cfg)

    assert len(selected) == 1
    assert len(rejected) == 1
    assert rejected[0].rejection_reasons[0].value == "duplicate_symbol"


def test_selector_enforces_unique_setup_tuple() -> None:
    cfg = DecisionConfig(
        selection_policy=SelectionPolicyConfig(
            enforce_unique_symbol=False,
            enforce_unique_symbol_timeframe_strategy=True,
        )
    )
    candidates = [
        _pick("INFY.NS", DecisionHorizon.SWING, 90, 2.0, timeframe="1D", strategy="S1"),
        _pick("INFY.NS", DecisionHorizon.SWING, 89, 2.0, timeframe="1D", strategy="S1"),
    ]
    selected, rejected = PortfolioCandidateSelector().select(candidates, cfg)

    assert len(selected) == 1
    assert len(rejected) == 1
    assert rejected[0].rejection_reasons[0].value == "duplicate_setup"
