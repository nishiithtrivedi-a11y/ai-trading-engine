"""
Sector rotation analytics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.core.data_handler import DataHandler
from src.market_intelligence.config import SectorRotationConfig
from src.market_intelligence.models import SectorRotationState, SectorStrengthSnapshot


class SectorRotationError(Exception):
    """Raised when sector rotation analysis cannot be computed."""


@dataclass
class SectorRotationAnalyzer:
    def analyze(
        self,
        sector_symbol_map: dict[str, list[str]],
        data_by_symbol: dict[str, DataHandler],
        config: SectorRotationConfig,
        benchmark_data: Optional[DataHandler] = None,
    ) -> list[SectorStrengthSnapshot]:
        if not sector_symbol_map:
            return []

        benchmark_returns = (
            self._compute_weighted_returns(benchmark_data, config.lookback_windows, config.lookback_weights)
            if benchmark_data is not None
            else {}
        )
        benchmark_weighted = sum(
            benchmark_returns.get(window, 0.0) * config.lookback_weights.get(window, 0.0)
            for window in config.lookback_windows
        )

        sector_rows: list[SectorStrengthSnapshot] = []
        for sector, symbols in sector_symbol_map.items():
            symbol_returns: dict[str, dict[int, float]] = {}
            symbol_scores: dict[str, float] = {}

            for symbol in symbols:
                dh = data_by_symbol.get(symbol)
                if dh is None:
                    continue
                returns = self._compute_weighted_returns(
                    dh,
                    config.lookback_windows,
                    config.lookback_weights,
                )
                if not returns:
                    continue
                symbol_returns[symbol] = returns
                weighted = sum(
                    returns.get(window, 0.0) * config.lookback_weights.get(window, 0.0)
                    for window in config.lookback_windows
                )
                symbol_scores[symbol] = weighted

            if not symbol_scores:
                continue

            avg_lookback_returns: dict[str, float] = {}
            for window in config.lookback_windows:
                values = [r[window] for r in symbol_returns.values() if window in r]
                if values:
                    avg_lookback_returns[str(window)] = float(sum(values) / len(values))

            sector_weighted = float(sum(symbol_scores.values()) / len(symbol_scores))
            score = sector_weighted - benchmark_weighted if benchmark_returns else sector_weighted
            top_symbols = [
                k for k, _ in sorted(symbol_scores.items(), key=lambda x: x[1], reverse=True)[:3]
            ]

            sector_rows.append(
                SectorStrengthSnapshot(
                    sector=sector,
                    score=score,
                    benchmark_relative_return=(score if benchmark_returns else None),
                    lookback_returns=avg_lookback_returns,
                    top_symbols=top_symbols,
                    metadata={
                        "sector_weighted_return": sector_weighted,
                        "benchmark_weighted_return": benchmark_weighted if benchmark_returns else None,
                        "member_count": len(symbol_scores),
                    },
                )
            )

        ranked = sorted(sector_rows, key=lambda s: float(s.score), reverse=True)
        n = len(ranked)
        leading_count = max(1, int(round(n * config.leading_quantile))) if n > 0 else 0
        lagging_count = max(1, int(round(n * config.lagging_quantile))) if n > 0 else 0

        for idx, row in enumerate(ranked, start=1):
            row.rank = idx
            if idx <= leading_count:
                row.state = SectorRotationState.LEADING
            elif idx > n - lagging_count:
                row.state = SectorRotationState.LAGGING
            else:
                row.state = SectorRotationState.WEAKENING

        return ranked

    @staticmethod
    def _compute_weighted_returns(
        data_handler: Optional[DataHandler],
        lookback_windows: list[int],
        lookback_weights: dict[int, float],
    ) -> dict[int, float]:
        if data_handler is None:
            return {}
        close = data_handler.data["close"].astype(float)
        if len(close) < 2:
            return {}

        out: dict[int, float] = {}
        latest = float(close.iloc[-1])
        if latest <= 0:
            return {}

        for window in lookback_windows:
            if len(close) <= window:
                continue
            base = float(close.iloc[-1 - window])
            if base <= 0:
                continue
            out[window] = latest / base - 1.0
        if not out:
            return {}

        # Ensure windows present in weights are retained only.
        return {k: v for k, v in out.items() if k in lookback_weights}
