"""
Portfolio planning configuration for Phase 18.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.decision.portfolio_models import AllocationModel, SizingMethod


def normalize_allocation_model(value: AllocationModel | str) -> AllocationModel:
    if isinstance(value, AllocationModel):
        return value
    key = str(value).strip().lower()
    alias = {
        "equal_weight": AllocationModel.EQUAL_WEIGHT,
        "equal": AllocationModel.EQUAL_WEIGHT,
        "volatility_weighted": AllocationModel.VOLATILITY_WEIGHTED,
        "volatility": AllocationModel.VOLATILITY_WEIGHTED,
        "conviction_weighted": AllocationModel.CONVICTION_WEIGHTED,
        "conviction": AllocationModel.CONVICTION_WEIGHTED,
    }
    if key not in alias:
        raise ValueError(f"Unsupported allocation model '{value}'")
    return alias[key]


def normalize_sizing_method(value: SizingMethod | str) -> SizingMethod:
    if isinstance(value, SizingMethod):
        return value
    key = str(value).strip().lower()
    alias = {
        "fixed_fractional": SizingMethod.FIXED_FRACTIONAL,
        "fixed": SizingMethod.FIXED_FRACTIONAL,
        "risk_per_trade": SizingMethod.RISK_PER_TRADE,
        "risk": SizingMethod.RISK_PER_TRADE,
        "atr_based": SizingMethod.ATR_BASED,
        "atr": SizingMethod.ATR_BASED,
    }
    if key not in alias:
        raise ValueError(f"Unsupported sizing method '{value}'")
    return alias[key]


@dataclass
class PortfolioPlanningConfig:
    enabled: bool = True
    total_capital: float = 100_000.0
    reserve_cash_pct: float = 0.10

    allocation_model: AllocationModel = AllocationModel.CONVICTION_WEIGHTED
    sizing_method: SizingMethod = SizingMethod.RISK_PER_TRADE
    fixed_fractional_position_pct: float = 1.0
    risk_per_trade_pct: float = 0.01
    atr_fallback_stop_pct: float = 0.02

    max_capital_deployed_pct: float = 0.90
    max_positions: int = 8
    max_per_position_allocation_pct: float = 0.25
    max_per_trade_risk_pct: float = 0.02
    max_sector_exposure_pct: float = 0.40
    max_correlated_positions: int = 2

    drawdown_daily_reduce_risk_pct: float = 0.02
    drawdown_rolling_reduce_risk_pct: float = 0.07
    max_daily_drawdown_pct: float = 0.04
    max_rolling_drawdown_pct: float = 0.12
    reduce_risk_multiplier: float = 0.50
    pause_new_risk_on_severe_drawdown: bool = True

    def __post_init__(self) -> None:
        self.total_capital = float(self.total_capital)
        self.reserve_cash_pct = float(self.reserve_cash_pct)
        self.fixed_fractional_position_pct = float(self.fixed_fractional_position_pct)
        self.risk_per_trade_pct = float(self.risk_per_trade_pct)
        self.atr_fallback_stop_pct = float(self.atr_fallback_stop_pct)
        self.max_capital_deployed_pct = float(self.max_capital_deployed_pct)
        self.max_per_position_allocation_pct = float(self.max_per_position_allocation_pct)
        self.max_per_trade_risk_pct = float(self.max_per_trade_risk_pct)
        self.max_sector_exposure_pct = float(self.max_sector_exposure_pct)
        self.drawdown_daily_reduce_risk_pct = float(self.drawdown_daily_reduce_risk_pct)
        self.drawdown_rolling_reduce_risk_pct = float(self.drawdown_rolling_reduce_risk_pct)
        self.max_daily_drawdown_pct = float(self.max_daily_drawdown_pct)
        self.max_rolling_drawdown_pct = float(self.max_rolling_drawdown_pct)
        self.reduce_risk_multiplier = float(self.reduce_risk_multiplier)
        self.max_positions = int(self.max_positions)
        self.max_correlated_positions = int(self.max_correlated_positions)

        self.allocation_model = normalize_allocation_model(self.allocation_model)
        self.sizing_method = normalize_sizing_method(self.sizing_method)

        if self.total_capital <= 0:
            raise ValueError("total_capital must be > 0")
        if self.max_positions < 1:
            raise ValueError("max_positions must be >= 1")
        if self.max_correlated_positions < 1:
            raise ValueError("max_correlated_positions must be >= 1")

        self._validate_pct("reserve_cash_pct", self.reserve_cash_pct)
        self._validate_pct("fixed_fractional_position_pct", self.fixed_fractional_position_pct)
        self._validate_pct("risk_per_trade_pct", self.risk_per_trade_pct)
        self._validate_pct("atr_fallback_stop_pct", self.atr_fallback_stop_pct)
        self._validate_pct("max_capital_deployed_pct", self.max_capital_deployed_pct)
        self._validate_pct("max_per_position_allocation_pct", self.max_per_position_allocation_pct)
        self._validate_pct("max_per_trade_risk_pct", self.max_per_trade_risk_pct)
        self._validate_pct("max_sector_exposure_pct", self.max_sector_exposure_pct)
        self._validate_pct("drawdown_daily_reduce_risk_pct", self.drawdown_daily_reduce_risk_pct)
        self._validate_pct("drawdown_rolling_reduce_risk_pct", self.drawdown_rolling_reduce_risk_pct)
        self._validate_pct("max_daily_drawdown_pct", self.max_daily_drawdown_pct)
        self._validate_pct("max_rolling_drawdown_pct", self.max_rolling_drawdown_pct)
        self._validate_pct("reduce_risk_multiplier", self.reduce_risk_multiplier)

        if self.max_capital_deployed_pct + self.reserve_cash_pct > 1.0 + 1e-9:
            raise ValueError(
                "reserve_cash_pct + max_capital_deployed_pct must be <= 1.0 "
                "to avoid impossible allocation targets"
            )
        if self.drawdown_daily_reduce_risk_pct > self.max_daily_drawdown_pct:
            raise ValueError(
                "drawdown_daily_reduce_risk_pct cannot exceed max_daily_drawdown_pct"
            )
        if self.drawdown_rolling_reduce_risk_pct > self.max_rolling_drawdown_pct:
            raise ValueError(
                "drawdown_rolling_reduce_risk_pct cannot exceed max_rolling_drawdown_pct"
            )

    @staticmethod
    def _validate_pct(name: str, value: float) -> None:
        if not 0 <= value <= 1:
            raise ValueError(f"{name} must be in [0, 1]")

