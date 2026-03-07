"""
Configuration management for the backtesting engine.

Uses Pydantic for validated, typed configuration with sensible defaults.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class DataSource(str, Enum):
    """Where market data is loaded from."""
    CSV = "csv"
    INDIAN_CSV = "indian_csv"
    ZERODHA = "zerodha"
    UPSTOX = "upstox"


class ExecutionMode(str, Enum):
    """When signals are executed relative to the signal bar."""
    NEXT_BAR_OPEN = "next_bar_open"
    SAME_BAR_CLOSE = "same_bar_close"


class PositionSizingMethod(str, Enum):
    """How position size is determined."""
    FIXED_QUANTITY = "fixed_quantity"
    PERCENT_OF_EQUITY = "percent_of_equity"
    RISK_BASED = "risk_based"


class RiskConfig(BaseModel):
    """Risk management configuration."""
    stop_loss_pct: Optional[float] = Field(default=None, description="Stop loss as % of entry price (e.g., 0.02 = 2%)")
    take_profit_pct: Optional[float] = Field(default=None, description="Take profit as % of entry price")
    trailing_stop_pct: Optional[float] = Field(default=None, description="Trailing stop as % from peak")
    max_position_size_pct: float = Field(default=1.0, description="Max position as % of equity (1.0 = 100%)")
    max_risk_per_trade_pct: float = Field(default=0.02, description="Max risk per trade as % of equity")
    max_drawdown_kill_pct: Optional[float] = Field(default=None, description="Kill switch: stop trading if drawdown exceeds this %")

    @field_validator("stop_loss_pct", "take_profit_pct", "trailing_stop_pct")
    @classmethod
    def validate_positive_or_none(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v <= 0:
            raise ValueError("Must be positive or None")
        return v

    @field_validator("max_position_size_pct")
    @classmethod
    def validate_position_size(cls, v: float) -> float:
        if v <= 0 or v > 1.0:
            raise ValueError("Max position size must be between 0 (exclusive) and 1.0 (inclusive)")
        return v


class BacktestConfig(BaseModel):
    """Main backtesting configuration."""
    # Capital and costs
    initial_capital: float = Field(default=100_000.0, gt=0)
    fee_rate: float = Field(default=0.001, ge=0, description="Fee as fraction of trade value (0.001 = 0.1%)")
    slippage_rate: float = Field(default=0.0005, ge=0, description="Slippage as fraction of price (0.0005 = 0.05%)")

    # Execution
    execution_mode: ExecutionMode = Field(default=ExecutionMode.NEXT_BAR_OPEN)

    # Position sizing
    position_sizing: PositionSizingMethod = Field(default=PositionSizingMethod.PERCENT_OF_EQUITY)
    fixed_quantity: float = Field(default=100.0, gt=0)
    position_size_pct: float = Field(default=0.95, gt=0, le=1.0, description="Fraction of equity to use per trade")

    # Risk
    risk: RiskConfig = Field(default_factory=RiskConfig)

    # Data
    data_source: DataSource = Field(default=DataSource.CSV, description="Data source type")
    data_file: str = Field(default="data/sample_data.csv")

    # Annualization
    trading_days_per_year: int = Field(default=252, gt=0)
    risk_free_rate: float = Field(default=0.0, ge=0)

    # Behavior
    close_positions_at_end: bool = Field(default=True, description="Close all open positions at end of backtest")

    # Intraday mode
    intraday: bool = Field(default=False, description="Enable intraday session handling")
    market_timezone: str = Field(default="Asia/Kolkata", description="Timezone for intraday session logic")
    force_square_off_at_close: bool = Field(default=True, description="Force close positions at session end")
    allow_entries_only_during_market_hours: bool = Field(default=True, description="Block new entries outside market hours")

    # Strategy parameters (passed through to strategy)
    strategy_params: dict[str, Any] = Field(default_factory=dict)

    # Output
    output_dir: str = Field(default="output")

    @field_validator("data_file")
    @classmethod
    def validate_data_file_extension(cls, v: str, info) -> str:
        # API sources don't need a CSV file
        source = info.data.get("data_source", DataSource.CSV)
        if source in (DataSource.CSV, DataSource.INDIAN_CSV):
            if not v.endswith(".csv"):
                raise ValueError("Data file must be a .csv file")
        return v


def load_config(overrides: Optional[dict[str, Any]] = None) -> BacktestConfig:
    """Create a BacktestConfig, optionally overriding defaults.

    Args:
        overrides: Dict of config values to override defaults.

    Returns:
        Validated BacktestConfig instance.
    """
    if overrides is None:
        return BacktestConfig()
    return BacktestConfig(**overrides)
