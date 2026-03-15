"""
Fill price model for research simulations.

Models the price at which a trade is actually executed, given a signal
generated at bar T.

DESIGN PRINCIPLE
----------------
  - No live order routing.  Returns a hypothetical fill price from
    historical OHLCV data.
  - The default (and most realistic) fill is the *next bar's open price*,
    consistent with ``BacktestEngine``'s ``NEXT_BAR_OPEN`` execution mode.
  - A current-bar-close fill is supported for comparison purposes but is
    NOT recommended for research (it introduces look-ahead bias when the
    close is not yet known at signal time).

FILL MODES
----------
  use_next_bar_open=True  (default, recommended)
      Signal on bar T; fill at bar T+1 open.
      Mimics placing a market-at-open order overnight.

  use_next_bar_open=False
      Signal on bar T; fill at bar T close.
      Best for end-of-bar simulation; introduces slight look-ahead for
      strategies that react to intraday price moves.

FILL PRICE ADJUSTMENTS
----------------------
  The ``FillModel`` itself does not apply slippage -- that is handled by
  ``CostModel``.  The fill price returned here is the *raw* OHLCV price
  before any cost model adjustments.

PUBLIC API
----------
  FillConfig      Configuration for fill behaviour.
  FillModel       Main fill price calculation class.
  FillResult      Result of a single fill price lookup.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class FillConfig:
    """Fill model configuration.

    Parameters
    ----------
    use_next_bar_open : bool
        When True (default), fills use the next bar's open price.
        When False, fills use the current bar's close price.
    """

    use_next_bar_open: bool = True


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class FillResult:
    """Result of a single fill price lookup.

    Attributes
    ----------
    fill_price : float or None
        The raw fill price from OHLCV data.  None if fill cannot be
        determined (e.g. no next bar available).
    fill_mode : str
        Human-readable description: ``"next_bar_open"`` or ``"current_bar_close"``.
    bar_index : int
        The bar index whose price was used for the fill.
    available : bool
        True when a valid fill price was found.
    """

    fill_price: Optional[float]
    fill_mode: str
    bar_index: int
    available: bool


# ---------------------------------------------------------------------------
# Fill model
# ---------------------------------------------------------------------------

class FillModel:
    """Determine the hypothetical fill price for a signal.

    Parameters
    ----------
    config : FillConfig
        Fill configuration.  Defaults to next-bar-open mode.
    """

    def __init__(self, config: FillConfig | None = None) -> None:
        self.config = config or FillConfig()

    def get_fill_price(
        self,
        df: pd.DataFrame,
        signal_bar_idx: int,
        side: str = "buy",
    ) -> FillResult:
        """Return the fill price for a signal generated at ``signal_bar_idx``.

        Parameters
        ----------
        df : pd.DataFrame
            OHLCV DataFrame.  Must contain ``"open"`` and ``"close"`` columns.
            Index must be integer-positional (0-based) or the method uses
            ``iloc`` access.
        signal_bar_idx : int
            0-based index of the bar on which the signal was generated.
        side : str
            ``"buy"`` or ``"sell"`` (informational; fill price is the same
            for both in this simple model).

        Returns
        -------
        FillResult
            Fill price and metadata.  ``available=False`` when no fill can
            be obtained (e.g. signal on the last bar with next-bar mode).
        """
        n = len(df)

        if n == 0:
            return FillResult(
                fill_price=None, fill_mode="unavailable",
                bar_index=signal_bar_idx, available=False,
            )

        if self.config.use_next_bar_open:
            fill_bar = signal_bar_idx + 1
            if fill_bar >= n:
                # No next bar available (signal on last bar)
                return FillResult(
                    fill_price=None,
                    fill_mode="next_bar_open",
                    bar_index=fill_bar,
                    available=False,
                )
            price = float(df["open"].iloc[fill_bar])
            return FillResult(
                fill_price=price,
                fill_mode="next_bar_open",
                bar_index=fill_bar,
                available=True,
            )
        else:
            # Current bar close
            fill_bar = signal_bar_idx
            if fill_bar < 0 or fill_bar >= n:
                return FillResult(
                    fill_price=None,
                    fill_mode="current_bar_close",
                    bar_index=fill_bar,
                    available=False,
                )
            price = float(df["close"].iloc[fill_bar])
            return FillResult(
                fill_price=price,
                fill_mode="current_bar_close",
                bar_index=fill_bar,
                available=True,
            )

    def get_fill_price_at_date(
        self,
        df: pd.DataFrame,
        signal_timestamp: pd.Timestamp,
        side: str = "buy",
    ) -> FillResult:
        """Convenience wrapper: look up fill price by timestamp rather than integer index.

        Finds the bar whose index matches ``signal_timestamp`` (or the nearest
        subsequent bar) and delegates to ``get_fill_price()``.

        Parameters
        ----------
        df : pd.DataFrame
            OHLCV DataFrame with a DatetimeIndex.
        signal_timestamp : pd.Timestamp
            The timestamp of the bar that generated the signal.
        side : str
            ``"buy"`` or ``"sell"``.

        Returns
        -------
        FillResult
            Fill price and metadata.
        """
        if df.empty:
            return FillResult(
                fill_price=None, fill_mode="unavailable",
                bar_index=-1, available=False,
            )

        # Locate the signal bar by timestamp
        try:
            signal_bar_idx = df.index.get_loc(signal_timestamp)
            if not isinstance(signal_bar_idx, int):
                # Slice / mask returned -- use the first match
                signal_bar_idx = int(signal_bar_idx.start)  # type: ignore[union-attr]
        except KeyError:
            # Timestamp not found; fall back to positional last bar
            return FillResult(
                fill_price=None, fill_mode="timestamp_not_found",
                bar_index=-1, available=False,
            )

        return self.get_fill_price(df, signal_bar_idx, side=side)
