"""
Risk management package for portfolio-level guardrails.

Provides PortfolioRiskConfig, PositionSizer, and PortfolioRiskManager
for pre-trade risk checks, position sizing, and drawdown monitoring.

Note on naming: ``RiskConfig`` already exists in ``src.utils.config``
(per-trade stop-loss / take-profit configuration for BacktestEngine).
This package provides *portfolio-level* risk management with a separate
``PortfolioRiskConfig`` to avoid naming conflicts.
"""

from .risk_engine import (
    PortfolioRiskConfig,
    PositionSizer,
    RiskDecision,
    PortfolioRiskManager,
    validate_portfolio_risk,
    generate_risk_report,
)

__all__ = [
    "PortfolioRiskConfig",
    "PositionSizer",
    "RiskDecision",
    "PortfolioRiskManager",
    "validate_portfolio_risk",
    "generate_risk_report",
]
