"""
Relative and sector strength analysis for Phase 4 monitoring.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

from src.monitoring.config import RelativeStrengthConfig
from src.monitoring.models import RelativeStrengthSnapshot, SectorStrengthSnapshot
from src.scanners.data_gateway import DataGateway


class SectorStrengthAnalyzerError(Exception):
    """Raised when relative/sector strength analysis fails."""


@dataclass
class SectorStrengthAnalyzer:
    def analyze(
        self,
        symbols: list[str],
        data_gateway: DataGateway,
        config: RelativeStrengthConfig,
        timeframe: Optional[str] = None,
        sector_map: Optional[dict[str, str]] = None,
    ) -> tuple[list[RelativeStrengthSnapshot], list[SectorStrengthSnapshot]]:
        if not symbols:
            return [], []

        tf = timeframe or config.timeframe
        benchmark_returns = self._load_benchmark_returns(data_gateway, config, tf)

        snapshots: list[RelativeStrengthSnapshot] = []
        for symbol in symbols:
            try:
                dh = data_gateway.load_data(symbol, tf)
            except Exception:
                continue

            lookback_returns = self._compute_lookback_returns(dh.data["close"], config.lookback_windows)
            if not lookback_returns:
                continue

            effective_weights = self._effective_weights(config.lookback_weights, lookback_returns.keys())
            weighted_absolute = sum(lookback_returns[w] * effective_weights[w] for w in effective_weights)

            relative_return = None
            if benchmark_returns:
                weighted_benchmark = sum(
                    benchmark_returns.get(w, 0.0) * effective_weights.get(w, 0.0) for w in effective_weights
                )
                relative_return = weighted_absolute - weighted_benchmark
                score = relative_return
            else:
                score = weighted_absolute

            snapshots.append(
                RelativeStrengthSnapshot(
                    symbol=symbol,
                    score=float(score),
                    lookback_returns={str(k): float(v) for k, v in lookback_returns.items()},
                    benchmark_symbol=config.benchmark_symbol if benchmark_returns else None,
                    relative_return=relative_return,
                    sector=(sector_map or {}).get(symbol),
                )
            )

        ranked = sorted(snapshots, key=lambda s: float(s.score), reverse=True)
        for idx, snap in enumerate(ranked, start=1):
            snap.rank = idx

        sector_rows = self._build_sector_strength(ranked, sector_map or {})
        return ranked[: config.top_n], sector_rows

    @staticmethod
    def load_sector_map(path: str | Path) -> dict[str, str]:
        path_obj = Path(path)
        if not path_obj.exists():
            raise SectorStrengthAnalyzerError(f"Sector map file not found: {path_obj}")

        suffix = path_obj.suffix.lower()
        if suffix == ".json":
            try:
                payload = json.loads(path_obj.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                raise SectorStrengthAnalyzerError(
                    f"Failed to parse sector map JSON {path_obj}: {exc}"
                ) from exc
            if not isinstance(payload, dict):
                raise SectorStrengthAnalyzerError("Sector map JSON must be an object of symbol -> sector")
            return {str(k).strip().upper(): str(v).strip() for k, v in payload.items() if str(v).strip()}

        if suffix == ".csv":
            try:
                df = pd.read_csv(path_obj)
            except Exception as exc:  # noqa: BLE001
                raise SectorStrengthAnalyzerError(f"Failed to read sector map CSV {path_obj}: {exc}") from exc

            if "symbol" not in df.columns or "sector" not in df.columns:
                raise SectorStrengthAnalyzerError("Sector CSV must contain 'symbol' and 'sector' columns")

            rows = (
                df[["symbol", "sector"]]
                .dropna()
                .astype(str)
                .assign(symbol=lambda x: x["symbol"].str.strip().str.upper())
                .assign(sector=lambda x: x["sector"].str.strip())
            )
            return {
                row["symbol"]: row["sector"]
                for _, row in rows.iterrows()
                if row["symbol"] and row["sector"]
            }

        raise SectorStrengthAnalyzerError(
            f"Unsupported sector map format '{suffix}'. Supported: .csv, .json"
        )

    @staticmethod
    def _compute_lookback_returns(close: pd.Series, windows: list[int]) -> dict[int, float]:
        returns: dict[int, float] = {}
        if close.empty:
            return returns
        latest = float(close.iloc[-1])
        if latest <= 0:
            return returns

        for window in windows:
            if len(close) <= window:
                continue
            base = float(close.iloc[-1 - window])
            if base <= 0:
                continue
            returns[int(window)] = latest / base - 1.0
        return returns

    @staticmethod
    def _effective_weights(
        configured_weights: dict[int, float],
        available_windows: Iterable[int],
    ) -> dict[int, float]:
        available = {int(w) for w in available_windows}
        filtered = {int(w): float(v) for w, v in configured_weights.items() if int(w) in available}
        total = sum(filtered.values())
        if total <= 0:
            equal = 1.0 / len(available) if available else 0.0
            return {int(w): equal for w in sorted(available)}
        return {k: v / total for k, v in filtered.items()}

    def _load_benchmark_returns(
        self,
        data_gateway: DataGateway,
        config: RelativeStrengthConfig,
        timeframe: str,
    ) -> dict[int, float]:
        try:
            benchmark_data = data_gateway.load_data(config.benchmark_symbol, timeframe)
            return self._compute_lookback_returns(
                benchmark_data.data["close"],
                config.lookback_windows,
            )
        except Exception as exc:  # noqa: BLE001
            if config.allow_missing_benchmark:
                return {}
            raise SectorStrengthAnalyzerError(
                f"Failed to load benchmark {config.benchmark_symbol}: {exc}"
            ) from exc

    @staticmethod
    def _build_sector_strength(
        ranked: list[RelativeStrengthSnapshot],
        sector_map: dict[str, str],
    ) -> list[SectorStrengthSnapshot]:
        grouped: dict[str, list[RelativeStrengthSnapshot]] = defaultdict(list)
        for row in ranked:
            sector = sector_map.get(row.symbol) or row.sector
            if not sector:
                continue
            grouped[sector].append(row)

        snapshots: list[SectorStrengthSnapshot] = []
        for sector, rows in grouped.items():
            score = sum(float(r.score) for r in rows) / len(rows)
            top_symbols = [r.symbol for r in sorted(rows, key=lambda x: float(x.score), reverse=True)[:3]]
            snapshots.append(
                SectorStrengthSnapshot(
                    sector=sector,
                    score=score,
                    member_count=len(rows),
                    top_symbols=top_symbols,
                )
            )

        ranked_sectors = sorted(snapshots, key=lambda s: float(s.score), reverse=True)
        for idx, row in enumerate(ranked_sectors, start=1):
            row.rank = idx
        return ranked_sectors
