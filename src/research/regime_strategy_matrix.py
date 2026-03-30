"""
Research helpers for professional regime x strategy matrix analysis.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.market_intelligence.professional_regime import PROFESSIONAL_REGIME_ORDER


def infer_strategy_archetype(strategy_key: str) -> str:
    key = str(strategy_key).strip().lower()
    if "reversion" in key or "fade" in key or "pivot" in key:
        return "mean_reversion"
    if "breakout" in key or "range_break" in key:
        return "breakout"
    if "trend" in key or "momentum" in key or "pullback" in key:
        return "trend_pullback"
    if "regime" in key:
        return "regime_adaptive"
    if "gap" in key:
        return "gap_opening"
    if "volume" in key:
        return "volume_momentum"
    return "other"


def _safe_numeric(series: pd.Series, fill: float = 0.0) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    numeric = numeric.replace([float("inf"), float("-inf")], np.nan)
    return numeric.fillna(fill).astype(float)


def build_regime_strategy_summary(results_df: pd.DataFrame) -> pd.DataFrame:
    required = {"regime_label", "strategy", "symbol", "timeframe", "window_id"}
    missing = required - set(results_df.columns)
    if missing:
        raise ValueError(f"results_df missing required columns: {sorted(missing)}")

    df = results_df.copy()
    df["total_return_pct"] = _safe_numeric(df.get("total_return_pct", pd.Series(dtype=float)))
    df["max_drawdown_pct"] = _safe_numeric(df.get("max_drawdown_pct", pd.Series(dtype=float)))
    df["profit_factor"] = _safe_numeric(df.get("profit_factor", pd.Series(dtype=float)))
    df["expectancy"] = _safe_numeric(df.get("expectancy", pd.Series(dtype=float)))
    df["sharpe_ratio"] = _safe_numeric(df.get("sharpe_ratio", pd.Series(dtype=float)))
    df["num_trades"] = _safe_numeric(df.get("num_trades", pd.Series(dtype=float)))
    df["win_rate"] = _safe_numeric(df.get("win_rate", pd.Series(dtype=float)))
    df["exposure_pct"] = _safe_numeric(df.get("exposure_pct", pd.Series(dtype=float)))
    df["avg_bars_held"] = _safe_numeric(df.get("avg_bars_held", pd.Series(dtype=float)))
    df["return_pct_points"] = df["total_return_pct"] * 100.0
    df["drawdown_pct_points"] = df["max_drawdown_pct"].abs() * 100.0
    df["win_rate_pct"] = df["win_rate"] * 100.0
    df["exposure_pct_points"] = df["exposure_pct"] * 100.0
    df["is_positive_run"] = (df["total_return_pct"] > 0).astype(float)

    group_cols = ["regime_label", "strategy", "archetype"]
    agg = (
        df.groupby(group_cols, dropna=False)
        .agg(
            run_count=("unit_key", "count"),
            symbol_count=("symbol", "nunique"),
            timeframe_count=("timeframe", "nunique"),
            window_count=("window_id", "nunique"),
            total_trades=("num_trades", "sum"),
            mean_return_pct=("return_pct_points", "mean"),
            median_return_pct=("return_pct_points", "median"),
            mean_drawdown_pct=("drawdown_pct_points", "mean"),
            mean_profit_factor=("profit_factor", "mean"),
            mean_expectancy=("expectancy", "mean"),
            mean_sharpe=("sharpe_ratio", "mean"),
            mean_win_rate_pct=("win_rate_pct", "mean"),
            positive_run_rate=("is_positive_run", "mean"),
            mean_exposure_pct=("exposure_pct_points", "mean"),
            mean_avg_bars_held=("avg_bars_held", "mean"),
        )
        .reset_index()
    )

    agg["stability_score"] = (
        agg["symbol_count"].clip(lower=0).div(4.0).clip(upper=1.0) * 0.40
        + agg["window_count"].clip(lower=0).div(3.0).clip(upper=1.0) * 0.30
        + agg["timeframe_count"].clip(lower=0).div(2.0).clip(upper=1.0) * 0.30
    )

    agg["balanced_score"] = (
        agg["mean_return_pct"] * 0.40
        + agg["mean_sharpe"] * 12.0
        + (agg["mean_profit_factor"].clip(lower=0.0, upper=3.0) - 1.0) * 18.0
        + agg["mean_expectancy"] * 8.0
        + agg["mean_win_rate_pct"] * 0.25
        + agg["positive_run_rate"] * 10.0
        + agg["stability_score"] * 15.0
        - agg["mean_drawdown_pct"] * 0.45
    )

    agg["confidence_flag"] = agg.apply(_confidence_flag, axis=1)
    numeric_cols = list(agg.select_dtypes(include=["float", "int"]).columns)
    agg[numeric_cols] = agg[numeric_cols].round(4)
    return agg.sort_values(["regime_label", "balanced_score"], ascending=[True, False]).reset_index(drop=True)


def _confidence_flag(row: pd.Series) -> str:
    run_count = int(row.get("run_count", 0) or 0)
    total_trades = float(row.get("total_trades", 0.0) or 0.0)
    stability = float(row.get("stability_score", 0.0) or 0.0)
    mean_pf = float(row.get("mean_profit_factor", 0.0) or 0.0)
    pos_rate = float(row.get("positive_run_rate", 0.0) or 0.0)
    mean_ret = float(row.get("mean_return_pct", 0.0) or 0.0)
    mean_dd = float(row.get("mean_drawdown_pct", 0.0) or 0.0)

    if run_count < 3 or total_trades < 20:
        return "insufficient_sample"
    if stability < 0.45:
        return "unstable"
    if mean_pf >= 1.10 and pos_rate >= 0.55 and mean_ret > 0 and mean_dd <= 12.0:
        return "strong_candidate"
    return "weak_candidate"


def select_top_candidates_by_regime(
    summary_df: pd.DataFrame,
    *,
    top_n: int = 2,
) -> pd.DataFrame:
    if summary_df.empty:
        return pd.DataFrame(
            columns=[
                "regime_label",
                "candidate_rank",
                "strategy",
                "archetype",
                "balanced_score",
                "confidence_flag",
                "selection_status",
            ]
        )

    rows: list[dict[str, Any]] = []
    regime_values = [r.value for r in PROFESSIONAL_REGIME_ORDER]
    for regime in regime_values:
        sub = summary_df[summary_df["regime_label"] == regime].copy()
        if sub.empty:
            rows.append(
                {
                    "regime_label": regime,
                    "candidate_rank": 1,
                    "strategy": None,
                    "archetype": None,
                    "balanced_score": None,
                    "confidence_flag": "no_candidate",
                    "selection_status": "no_data",
                }
            )
            continue

        sub = sub.sort_values(
            ["balanced_score", "total_trades", "run_count"],
            ascending=[False, False, False],
        ).head(max(top_n, 1))
        for rank_idx, (_, row) in enumerate(sub.iterrows(), start=1):
            confidence = str(row.get("confidence_flag", "weak_candidate"))
            mean_return_pct = float(row.get("mean_return_pct", 0.0) or 0.0)
            mean_profit_factor = float(row.get("mean_profit_factor", 0.0) or 0.0)
            total_trades = float(row.get("total_trades", 0.0) or 0.0)
            positive_run_rate = float(row.get("positive_run_rate", 0.0) or 0.0)
            viability_gate = (
                mean_return_pct > 0.0
                and mean_profit_factor >= 1.0
                and total_trades >= 30.0
                and positive_run_rate >= 0.50
            )
            selection_status = (
                "selected"
                if confidence in {"strong_candidate", "weak_candidate", "unstable"} and viability_gate
                else "insufficient"
            )
            rows.append(
                {
                    "regime_label": regime,
                    "candidate_rank": rank_idx,
                    "strategy": row["strategy"],
                    "archetype": row.get("archetype"),
                    "balanced_score": row.get("balanced_score"),
                    "confidence_flag": confidence,
                    "selection_status": selection_status,
                    "mean_return_pct": row.get("mean_return_pct"),
                    "mean_drawdown_pct": row.get("mean_drawdown_pct"),
                    "mean_profit_factor": row.get("mean_profit_factor"),
                    "mean_expectancy": row.get("mean_expectancy"),
                    "mean_sharpe": row.get("mean_sharpe"),
                    "total_trades": row.get("total_trades"),
                    "run_count": row.get("run_count"),
                    "symbol_count": row.get("symbol_count"),
                    "timeframe_count": row.get("timeframe_count"),
                    "window_count": row.get("window_count"),
                    "positive_run_rate": row.get("positive_run_rate"),
                    "stability_score": row.get("stability_score"),
                }
            )
    return pd.DataFrame(rows)


def build_regime_strategy_matrix(
    summary_df: pd.DataFrame,
    *,
    value_col: str = "balanced_score",
) -> pd.DataFrame:
    if summary_df.empty:
        return pd.DataFrame()
    matrix = summary_df.pivot_table(
        index="strategy",
        columns="regime_label",
        values=value_col,
        aggfunc="mean",
    )
    ordered_cols = [r.value for r in PROFESSIONAL_REGIME_ORDER if r.value in matrix.columns]
    matrix = matrix.reindex(columns=ordered_cols)
    return matrix.reset_index()


def write_research_markdown(
    *,
    summary_df: pd.DataFrame,
    candidates_df: pd.DataFrame,
    excluded_df: pd.DataFrame,
    output_path: str | Path,
    metadata: dict[str, Any],
) -> Path:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("# Regime x Strategy Matrix Research")
    lines.append("")
    lines.append("## Run Metadata")
    lines.append("")
    for key, value in metadata.items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## Top Candidates By Regime")
    lines.append("")

    for regime in [r.value for r in PROFESSIONAL_REGIME_ORDER]:
        sub = candidates_df[candidates_df["regime_label"] == regime]
        lines.append(f"### {regime}")
        if sub.empty:
            lines.append("- no candidate")
            lines.append("")
            continue
        for _, row in sub.iterrows():
            strategy = row.get("strategy") or "N/A"
            status = row.get("selection_status", "unknown")
            conf = row.get("confidence_flag", "unknown")
            score = row.get("balanced_score")
            score_txt = "N/A" if pd.isna(score) else f"{float(score):.4f}"
            lines.append(
                f"- rank {int(row.get('candidate_rank', 0))}: {strategy} "
                f"(status={status}, confidence={conf}, score={score_txt})"
            )
        lines.append("")

    weak = summary_df[summary_df["confidence_flag"].isin(["insufficient_sample", "weak_candidate"])]
    lines.append("## Weak / Rejected")
    lines.append("")
    if weak.empty and excluded_df.empty:
        lines.append("- none")
    else:
        if not weak.empty:
            for _, row in weak.sort_values(["regime_label", "balanced_score"]).iterrows():
                lines.append(
                    f"- {row['strategy']} in {row['regime_label']}: "
                    f"confidence={row['confidence_flag']} score={float(row['balanced_score']):.4f}"
                )
        if not excluded_df.empty:
            for _, row in excluded_df.iterrows():
                lines.append(
                    f"- excluded {row.get('strategy_key', row.get('file_name', 'unknown'))}: "
                    f"{row.get('reason', 'unspecified')}"
                )

    out.write_text("\n".join(lines), encoding="utf-8")
    return out
