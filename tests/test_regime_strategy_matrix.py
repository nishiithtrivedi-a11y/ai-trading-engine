from __future__ import annotations

import pandas as pd

from src.research.regime_strategy_matrix import (
    build_regime_strategy_matrix,
    build_regime_strategy_summary,
    infer_strategy_archetype,
    select_top_candidates_by_regime,
)


def _sample_results_df() -> pd.DataFrame:
    rows = []
    for idx in range(6):
        rows.append(
            {
                "unit_key": f"u{idx}",
                "symbol": "RELIANCE" if idx % 2 == 0 else "INFY",
                "timeframe": "5m" if idx < 3 else "15m",
                "window_id": f"W{1 + idx % 3}",
                "strategy": "codex_intraday_trend_reentry" if idx < 3 else "vwap_mean_reversion",
                "archetype": "trend_pullback" if idx < 3 else "mean_reversion",
                "regime_label": "BULL_TREND" if idx < 3 else "SIDEWAYS_RANGE",
                "total_return_pct": 0.02 if idx < 3 else 0.01,
                "max_drawdown_pct": -0.01 if idx < 3 else -0.015,
                "profit_factor": 1.4 if idx < 3 else 1.2,
                "expectancy": 0.15 if idx < 3 else 0.08,
                "sharpe_ratio": 1.1 if idx < 3 else 0.7,
                "num_trades": 12 if idx < 3 else 10,
                "win_rate": 0.56 if idx < 3 else 0.52,
                "exposure_pct": 0.45 if idx < 3 else 0.38,
                "avg_bars_held": 9 if idx < 3 else 7,
            }
        )
    return pd.DataFrame(rows)


def test_infer_strategy_archetype() -> None:
    assert infer_strategy_archetype("gap_fade") == "mean_reversion"
    assert infer_strategy_archetype("opening_range_breakout") == "breakout"
    assert infer_strategy_archetype("codex_intraday_trend_reentry") == "trend_pullback"


def test_build_summary_and_candidates() -> None:
    df = _sample_results_df()
    summary = build_regime_strategy_summary(df)
    assert not summary.empty
    assert {"regime_label", "strategy", "balanced_score", "confidence_flag"}.issubset(summary.columns)

    candidates = select_top_candidates_by_regime(summary, top_n=2)
    assert not candidates.empty
    assert "selection_status" in candidates.columns


def test_candidates_do_not_select_non_viable_rows() -> None:
    df = pd.DataFrame(
        [
            {
                "unit_key": f"u{idx}",
                "symbol": "RELIANCE",
                "timeframe": "5m",
                "window_id": f"W{idx}",
                "strategy": "test_strategy",
                "archetype": "breakout",
                "regime_label": "BEAR_TREND",
                "total_return_pct": -0.01,
                "max_drawdown_pct": -0.02,
                "profit_factor": float("inf"),
                "expectancy": -0.5,
                "sharpe_ratio": -0.2,
                "num_trades": 15,
                "win_rate": 0.3,
                "exposure_pct": 0.2,
                "avg_bars_held": 5,
            }
            for idx in range(3)
        ]
    )
    summary = build_regime_strategy_summary(df)
    row = summary.iloc[0]
    assert row["mean_profit_factor"] == 0.0

    candidates = select_top_candidates_by_regime(summary, top_n=1)
    selected = candidates[candidates["regime_label"] == "BEAR_TREND"].iloc[0]
    assert selected["selection_status"] == "insufficient"


def test_build_matrix_table() -> None:
    summary = build_regime_strategy_summary(_sample_results_df())
    matrix = build_regime_strategy_matrix(summary)
    assert "strategy" in matrix.columns
    assert not matrix.empty
