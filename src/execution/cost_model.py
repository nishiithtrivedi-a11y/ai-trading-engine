"""
Execution cost modelling for research simulations.

Computes realistic trade costs (commissions + slippage) to convert
gross backtest P&L into net P&L estimates.

DESIGN PRINCIPLE
----------------
  - Pure calculation layer; no order routing or live API calls.
  - Accepts per-trade inputs and returns a ``TradeCost`` breakdown.
  - Used by ``ExecutionCostAnalyzer`` to annotate existing trade logs.

COST COMPONENTS
---------------
  1. Fixed commission per trade (``commission_per_trade``) -- covers
     minimum brokerage, regulatory fees, etc.

  2. Proportional commission (``commission_bps``) -- expressed in basis
     points of notional value (1 bps = 0.01%).
     Formula: notional * commission_bps / 10_000

  3. Slippage (``slippage_bps``) -- models market impact / bid-ask
     spread as a fraction of notional value.
     For buy : fill_price = price * (1 + slippage_bps / 10_000)
     For sell: fill_price = price * (1 - slippage_bps / 10_000)
     Slippage cost = abs(fill_price - price) * quantity

  Total cost per side = commission + slippage_cost
  Full round-trip cost = entry_cost + exit_cost

DEFAULTS
--------
  commission_per_trade : 0.0    (many Zerodha/discount brokers charge 0)
  commission_bps       : 10.0   (10 bps = 0.10% -- typical Indian equity)
  slippage_bps         : 5.0    ( 5 bps = 0.05% -- half-spread estimate)

PUBLIC API
----------
  CostConfig     Configuration for cost parameters.
  TradeCost      Breakdown of a single-side cost computation.
  CostModel      Main cost computation class.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class CostConfig:
    """Cost model configuration.

    All bps values are expressed in *basis points* (1 bps = 0.01%).
    Use 10 bps for 0.10% and so on.

    Parameters
    ----------
    commission_per_trade : float
        Fixed monetary fee per trade leg (e.g. 20.0 for Rs. 20).
        Applied per side (entry and exit are separate trades).
    commission_bps : float
        Variable commission as basis points of notional (default: 10 bps).
        Example: 100 shares @ Rs 500 with 10 bps -> 0.10% of 50_000 = Rs 50.
    slippage_bps : float
        Slippage (market impact / bid-ask spread) as basis points of notional
        (default: 5 bps).  Applied to the fill price direction:
        buys fill at a higher price; sells at a lower price.
    """

    commission_per_trade: float = 0.0
    commission_bps: float = 10.0
    slippage_bps: float = 5.0

    def __post_init__(self) -> None:
        if self.commission_per_trade < 0:
            raise ValueError("commission_per_trade must be >= 0")
        if self.commission_bps < 0:
            raise ValueError("commission_bps must be >= 0")
        if self.slippage_bps < 0:
            raise ValueError("slippage_bps must be >= 0")


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class TradeCost:
    """Cost breakdown for a single trade leg.

    Attributes
    ----------
    notional : float
        Raw trade value: ``price * quantity``.
    commission : float
        Total commission = ``commission_per_trade + notional * commission_bps / 10_000``.
    slippage_cost : float
        Monetary slippage = ``abs(fill_price - price) * quantity``.
    total_cost : float
        ``commission + slippage_cost``; the all-in cost for this trade leg.
    fill_price : float
        Slippage-adjusted execution price.
        Buy : ``price * (1 + slippage_bps / 10_000)``
        Sell: ``price * (1 - slippage_bps / 10_000)``
    """

    notional: float
    commission: float
    slippage_cost: float
    total_cost: float
    fill_price: float


# ---------------------------------------------------------------------------
# Cost model
# ---------------------------------------------------------------------------

class CostModel:
    """Compute realistic trade costs from a price, quantity, and direction.

    Parameters
    ----------
    config : CostConfig
        Cost parameters (commission and slippage rates).
    """

    def __init__(self, config: CostConfig | None = None) -> None:
        self.config = config or CostConfig()

    def compute(
        self,
        price: float,
        quantity: float,
        side: Literal["buy", "sell"] = "buy",
    ) -> TradeCost:
        """Compute the full cost breakdown for one trade leg.

        Parameters
        ----------
        price : float
            Reference price (e.g. entry or exit price from the backtest).
        quantity : float
            Number of units traded (absolute value).
        side : str
            ``"buy"`` or ``"sell"``.  Slippage pushes buys up and sells down.

        Returns
        -------
        TradeCost
            Full breakdown of notional, commission, slippage, and net fill.
        """
        qty = abs(quantity)
        cfg = self.config

        # --- Notional ---
        notional = price * qty

        # --- Commission ---
        bps_comm = notional * cfg.commission_bps / 10_000.0
        commission = cfg.commission_per_trade + bps_comm

        # --- Slippage (applied to fill price direction) ---
        slip_frac = cfg.slippage_bps / 10_000.0
        if side == "buy":
            fill_price = price * (1.0 + slip_frac)
        else:
            fill_price = price * (1.0 - slip_frac)

        slippage_cost = abs(fill_price - price) * qty

        # --- Total ---
        total_cost = commission + slippage_cost

        return TradeCost(
            notional=notional,
            commission=commission,
            slippage_cost=slippage_cost,
            total_cost=total_cost,
            fill_price=fill_price,
        )

    def round_trip_cost(self, entry_price: float, exit_price: float, quantity: float) -> float:
        """Compute the total cost for a complete entry + exit round trip.

        Parameters
        ----------
        entry_price : float
            Price at which the position was opened (long entry = buy).
        exit_price : float
            Price at which the position was closed (long exit = sell).
        quantity : float
            Number of units (absolute value).

        Returns
        -------
        float
            Total cost in the same currency as the prices (e.g. Rs.).
        """
        entry_cost = self.compute(entry_price, quantity, side="buy")
        exit_cost  = self.compute(exit_price,  quantity, side="sell")
        return entry_cost.total_cost + exit_cost.total_cost
