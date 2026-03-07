"""
Main orchestrator for Phase 6 market intelligence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from src.core.data_handler import DataHandler
from src.market_intelligence.config import MarketIntelligenceConfig
from src.market_intelligence.institutional_flow import InstitutionalFlowAnalyzer
from src.market_intelligence.market_breadth import MarketBreadthAnalyzer
from src.market_intelligence.models import (
    BreadthState,
    MarketIntelligenceResult,
    MarketStateAssessment,
    RiskEnvironment,
    TrendState,
    VolatilityRegimeType,
)
from src.market_intelligence.sector_rotation import SectorRotationAnalyzer
from src.market_intelligence.volatility_regime import VolatilityRegimeAnalyzer
from src.market_intelligence.volume_intelligence import VolumeIntelligenceAnalyzer
from src.scanners.data_gateway import DataGateway
from src.strategies.base_strategy import BaseStrategy


class MarketStateEngineError(Exception):
    """Raised when market state orchestration fails."""


@dataclass
class MarketStateEngine:
    data_gateway: Optional[DataGateway] = None
    breadth_analyzer: Optional[MarketBreadthAnalyzer] = None
    sector_rotation_analyzer: Optional[SectorRotationAnalyzer] = None
    volume_analyzer: Optional[VolumeIntelligenceAnalyzer] = None
    volatility_analyzer: Optional[VolatilityRegimeAnalyzer] = None
    institutional_flow_analyzer: Optional[InstitutionalFlowAnalyzer] = None

    def __post_init__(self) -> None:
        self.breadth_analyzer = self.breadth_analyzer or MarketBreadthAnalyzer()
        self.sector_rotation_analyzer = self.sector_rotation_analyzer or SectorRotationAnalyzer()
        self.volume_analyzer = self.volume_analyzer or VolumeIntelligenceAnalyzer()
        self.volatility_analyzer = self.volatility_analyzer or VolatilityRegimeAnalyzer()
        self.institutional_flow_analyzer = self.institutional_flow_analyzer or InstitutionalFlowAnalyzer()

    def run(
        self,
        symbols: list[str],
        sector_symbol_map: dict[str, list[str]],
        config: MarketIntelligenceConfig,
        benchmark_symbol: Optional[str] = None,
    ) -> MarketIntelligenceResult:
        if not symbols:
            raise MarketStateEngineError("symbols cannot be empty")

        gateway = self.data_gateway or DataGateway(
            provider_name=config.provider_name,
            data_dir=config.data_dir,
        )

        warnings: list[str] = []
        errors: list[str] = []
        data_by_symbol: dict[str, DataHandler] = {}

        benchmark = benchmark_symbol or config.market_state.benchmark_symbol
        load_universe = list(dict.fromkeys(symbols + [benchmark]))

        for symbol in load_universe:
            try:
                data_by_symbol[symbol] = gateway.load_data(symbol, config.market_state.timeframe)
            except Exception as exc:  # noqa: BLE001
                message = f"failed to load data for {symbol}: {exc}"
                if config.continue_on_error:
                    warnings.append(message)
                    continue
                raise MarketStateEngineError(message) from exc

        symbol_data = {s: data_by_symbol[s] for s in symbols if s in data_by_symbol}
        if not symbol_data:
            raise MarketStateEngineError("No symbol data available for market intelligence run")

        benchmark_data = data_by_symbol.get(benchmark)
        if benchmark_data is None:
            warnings.append(f"benchmark data unavailable for {benchmark}; using first symbol proxy")
            benchmark_data = next(iter(symbol_data.values()))

        breadth_snapshot = self.breadth_analyzer.analyze(
            data_by_symbol=symbol_data,
            config=config.breadth,
            benchmark_symbol=benchmark,
        )

        sector_rotation = self.sector_rotation_analyzer.analyze(
            sector_symbol_map=sector_symbol_map,
            data_by_symbol=symbol_data,
            config=config.sector_rotation,
            benchmark_data=benchmark_data,
        )

        volume_analysis = self.volume_analyzer.analyze_many(
            data_by_symbol=symbol_data,
            config=config.volume,
        )

        volatility_snapshot = self.volatility_analyzer.detect(
            symbol=benchmark,
            data_handler=benchmark_data,
            config=config.volatility,
        )

        institutional_flow = self.institutional_flow_analyzer.analyze(config.institutional_flow)

        trend_state = self._trend_state(benchmark_data)
        risk_environment = self._risk_environment(
            breadth_state=breadth_snapshot.breadth_state,
            volatility_regime=volatility_snapshot.regime,
        )
        market_state = self._build_market_state(
            trend_state=trend_state,
            breadth_state=breadth_snapshot.breadth_state,
            sector_rotation=sector_rotation,
            volatility_regime=volatility_snapshot.regime,
            risk_environment=risk_environment,
            config=config,
        )

        return MarketIntelligenceResult(
            breadth_snapshot=breadth_snapshot,
            sector_rotation=sector_rotation,
            volume_analysis=volume_analysis,
            volatility_snapshot=volatility_snapshot,
            institutional_flow=institutional_flow,
            market_state=market_state,
            warnings=warnings,
            errors=errors,
        )

    @staticmethod
    def _trend_state(data_handler: DataHandler) -> TrendState:
        close = data_handler.data["close"].astype(float)
        if len(close) < 50:
            return TrendState.UNKNOWN

        sma20 = BaseStrategy.sma(close, 20).iloc[-1]
        sma50 = BaseStrategy.sma(close, 50).iloc[-1]
        last = float(close.iloc[-1])

        if pd.isna(sma20) or pd.isna(sma50):
            return TrendState.UNKNOWN
        if last > float(sma20) > float(sma50):
            return TrendState.BULLISH
        if last < float(sma20) < float(sma50):
            return TrendState.BEARISH
        return TrendState.RANGEBOUND

    @staticmethod
    def _risk_environment(
        breadth_state: BreadthState,
        volatility_regime: VolatilityRegimeType,
    ) -> RiskEnvironment:
        if volatility_regime in {VolatilityRegimeType.HIGH, VolatilityRegimeType.EXPANDING}:
            return RiskEnvironment.RISK_OFF
        if breadth_state == BreadthState.STRONG and volatility_regime in {
            VolatilityRegimeType.LOW,
            VolatilityRegimeType.CONTRACTION,
            VolatilityRegimeType.UNKNOWN,
        }:
            return RiskEnvironment.RISK_ON
        return RiskEnvironment.NEUTRAL

    @staticmethod
    def _state_to_score(value: str) -> float:
        mapping = {
            "bullish": 80.0,
            "bearish": 20.0,
            "rangebound": 50.0,
            "strong": 80.0,
            "weak": 20.0,
            "neutral": 50.0,
            "low_volatility": 75.0,
            "volatility_contraction": 70.0,
            "high_volatility": 25.0,
            "expanding_volatility": 35.0,
            "unknown": 50.0,
        }
        return mapping.get(value, 50.0)

    def _build_market_state(
        self,
        trend_state: TrendState,
        breadth_state: BreadthState,
        sector_rotation,
        volatility_regime: VolatilityRegimeType,
        risk_environment: RiskEnvironment,
        config: MarketIntelligenceConfig,
    ) -> MarketStateAssessment:
        leaders = [row.sector for row in sector_rotation if row.rank and row.rank <= 3]

        components = {
            "trend": self._state_to_score(trend_state.value),
            "breadth": self._state_to_score(breadth_state.value),
            "sector": 50.0 if not sector_rotation else max(0.0, min(100.0, 50.0 + sector_rotation[0].score * 100.0)),
            "volatility": self._state_to_score(volatility_regime.value),
        }

        weights = config.market_state.component_weights
        weighted = 0.0
        total = 0.0
        for key, value in components.items():
            w = float(weights.get(key, 0.0))
            if w <= 0:
                continue
            weighted += w * value
            total += w
        confidence = weighted / total if total > 0 else 50.0

        reasons = [
            f"trend_state={trend_state.value}",
            f"breadth_state={breadth_state.value}",
            f"volatility_regime={volatility_regime.value}",
        ]
        if leaders:
            reasons.append(f"sector_leaders={','.join(leaders[:3])}")

        return MarketStateAssessment(
            trend_state=trend_state,
            breadth_state=breadth_state,
            sector_leaders=leaders,
            volatility_regime=volatility_regime,
            risk_environment=risk_environment,
            confidence_score=confidence,
            summary_reasons=reasons,
            components=components,
        )
