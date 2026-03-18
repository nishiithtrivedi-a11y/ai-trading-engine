"""
Futures contract intelligence — resolution, analytics, and continuous series.

Provides:
- Active contract resolution from instrument registry
- Days-to-expiry calculation
- Roll proximity signals
- Continuous series scaffold (first-pass, research-grade)
- Front-vs-next contract context
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional


@dataclass
class FuturesContractInfo:
    """Structured information about a futures contract."""

    canonical: str
    underlying: str
    exchange: str
    expiry: date
    days_to_expiry: int
    contract_position: str         # "front", "next", "far"
    is_active: bool = True
    lot_size: Optional[int] = None
    tick_size: Optional[float] = None
    notes: list[str] = field(default_factory=list)


@dataclass
class FuturesContractFamily:
    """The set of active contracts for an underlying."""

    underlying: str
    exchange: str
    as_of: date
    contracts: list[FuturesContractInfo] = field(default_factory=list)

    @property
    def front(self) -> Optional[FuturesContractInfo]:
        return next(
            (c for c in self.contracts if c.contract_position == "front"), None
        )

    @property
    def next_contract(self) -> Optional[FuturesContractInfo]:
        return next(
            (c for c in self.contracts if c.contract_position == "next"), None
        )

    @property
    def is_roll_imminent(self) -> bool:
        """True if front contract expires within 5 days."""
        f = self.front
        return f is not None and f.days_to_expiry <= 5


@dataclass
class ContinuousSeriesMetadata:
    """Metadata for a continuous futures series stitching."""

    underlying: str
    exchange: str
    method: str                    # "calendar_roll", "volume_roll", etc.
    roll_dates: list[date] = field(default_factory=list)
    contract_spans: list[dict] = field(default_factory=list)  # [{from, to, contract}, ...]
    notes: list[str] = field(default_factory=list)


class FuturesContractResolver:
    """Resolve active futures contracts from an InstrumentRegistry.

    Provides contract family resolution, roll detection, and days-to-expiry.
    """

    def __init__(self, roll_day_threshold: int = 5):
        """Args:
            roll_day_threshold: Days before expiry to flag as "roll imminent".
        """
        self._roll_threshold = roll_day_threshold

    def get_contract_family(
        self,
        registry,
        underlying: str,
        exchange,
        as_of: Optional[date] = None,
    ) -> FuturesContractFamily:
        """Resolve the front/next/far contract family for an underlying.

        Args:
            registry: InstrumentRegistry instance.
            underlying: Underlying symbol (e.g., "NIFTY").
            exchange: Exchange enum or string.
            as_of: Reference date (today if None).

        Returns:
            FuturesContractFamily with labeled front/next/far contracts.
        """
        ref = as_of or date.today()

        futures = [
            i
            for i in registry.list_by_underlying(underlying)
            if i.instrument_type.value == "future"
            and i.expiry is not None
            and i.expiry >= ref
        ]
        futures.sort(key=lambda i: i.expiry)

        family = FuturesContractFamily(
            underlying=underlying.upper(),
            exchange=str(exchange),
            as_of=ref,
        )

        labels = ["front", "next", "far"]
        for i, inst in enumerate(futures[:3]):
            dte = (inst.expiry - ref).days
            label = labels[i] if i < len(labels) else f"far_{i}"
            family.contracts.append(
                FuturesContractInfo(
                    canonical=inst.canonical,
                    underlying=inst.symbol,
                    exchange=str(inst.exchange),
                    expiry=inst.expiry,
                    days_to_expiry=dte,
                    contract_position=label,
                    lot_size=inst.lot_size,
                    tick_size=inst.tick_size,
                )
            )

        return family

    def days_to_expiry(self, expiry: date, as_of: Optional[date] = None) -> int:
        """Return calendar days until expiry."""
        ref = as_of or date.today()
        return max(0, (expiry - ref).days)

    def is_roll_imminent(
        self, expiry: date, as_of: Optional[date] = None
    ) -> bool:
        """Return True if expiry is within roll_day_threshold days."""
        return self.days_to_expiry(expiry, as_of) <= self._roll_threshold

    def compute_basis(self, spot_price: float, futures_price: float) -> dict:
        """Compute futures basis metrics.

        Returns:
            dict with basis, basis_pct, contango (True if futures > spot).
        """
        basis = futures_price - spot_price
        basis_pct = (basis / spot_price * 100) if spot_price > 0 else 0.0
        return {
            "basis": basis,
            "basis_pct": basis_pct,
            "contango": basis > 0,
            "backwardation": basis < 0,
        }

    def get_roll_signal(self, family: FuturesContractFamily) -> dict:
        """Generate a roll proximity signal from a contract family."""
        front = family.front
        if front is None:
            return {"action": "no_front_contract", "imminent": False}

        return {
            "action": "roll_to_next"
            if family.is_roll_imminent
            else "hold_front",
            "imminent": family.is_roll_imminent,
            "front_dte": front.days_to_expiry,
            "front_expiry": str(front.expiry),
            "next_expiry": str(family.next_contract.expiry)
            if family.next_contract
            else None,
            "threshold_days": self._roll_threshold,
        }


class ContinuousSeriesBuilder:
    """Build a research-grade continuous futures series (scaffold).

    This is a first-pass implementation for research use.
    It does NOT implement a production-grade roll adjustment.

    Supported methods:
    - "calendar_roll": Roll on last trading day of expiry month.
    - "dte_roll": Roll N days before expiry.
    """

    def __init__(self, method: str = "dte_roll", roll_days: int = 5):
        self._method = method
        self._roll_days = roll_days

    def build_roll_schedule(
        self,
        contracts: list,  # list of Instrument sorted by expiry
        as_of: Optional[date] = None,
    ) -> ContinuousSeriesMetadata:
        """Build a roll schedule from a list of instruments.

        Returns ContinuousSeriesMetadata with roll_dates and contract_spans.
        Does not fetch or stitch data — returns structural metadata only.
        """
        ref = as_of or date.today()
        meta = ContinuousSeriesMetadata(
            underlying=contracts[0].symbol if contracts else "UNKNOWN",
            exchange=str(contracts[0].exchange) if contracts else "UNKNOWN",
            method=self._method,
            notes=[
                f"scaffold_only; method={self._method}; roll_days={self._roll_days}"
            ],
        )

        for i, inst in enumerate(contracts):
            if inst.expiry is None:
                continue

            if self._method == "dte_roll":
                roll_date = date(
                    inst.expiry.year,
                    inst.expiry.month,
                    max(1, inst.expiry.day - self._roll_days),
                )
            else:
                # calendar_roll: roll on expiry date itself
                roll_date = inst.expiry

            meta.roll_dates.append(roll_date)

            start = contracts[i - 1].expiry if i > 0 else ref
            meta.contract_spans.append(
                {
                    "contract": inst.canonical,
                    "from": str(start),
                    "to": str(roll_date),
                    "expiry": str(inst.expiry),
                }
            )

        return meta

    def stitch_from_dataframes(
        self,
        contract_data: dict,  # {canonical: pd.DataFrame}
        roll_schedule: ContinuousSeriesMetadata,
    ):
        """Stitch OHLCV DataFrames into a continuous series using the roll schedule.

        This is a simple forward-stitch (no price adjustment).
        Returns a combined DataFrame with a 'contract' column indicating source.
        """
        import pandas as pd

        frames = []
        for span in roll_schedule.contract_spans:
            canonical = span["contract"]
            if canonical not in contract_data:
                continue
            df = contract_data[canonical].copy()
            from_dt = pd.Timestamp(span["from"])
            to_dt = pd.Timestamp(span["to"])
            mask = (df.index >= from_dt) & (df.index <= to_dt)
            df = df[mask]
            df["contract"] = canonical
            frames.append(df)

        if not frames:
            import pandas as pd

            return pd.DataFrame()

        import pandas as pd

        return pd.concat(frames).sort_index()
