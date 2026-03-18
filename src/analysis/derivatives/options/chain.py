"""
Option chain builder — assembles, normalizes, and analyzes option chains.

Builds option chains from:
- DhanHQ option_chain API (when available)
- InstrumentRegistry + NormalizedQuote assembly (Kite path)
- Generic normalized dict input

Outputs normalized OptionChain objects suitable for downstream analytics.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional


@dataclass
class OptionStrike:
    """Normalized representation of a single strike's call/put data."""

    strike: float
    # Call (CE) side
    ce_ltp: Optional[float] = None
    ce_oi: Optional[int] = None
    ce_volume: Optional[int] = None
    ce_bid: Optional[float] = None
    ce_ask: Optional[float] = None
    ce_iv: Optional[float] = None
    ce_delta: Optional[float] = None
    ce_theta: Optional[float] = None
    ce_gamma: Optional[float] = None
    ce_vega: Optional[float] = None
    ce_source: str = "unknown"
    # Put (PE) side
    pe_ltp: Optional[float] = None
    pe_oi: Optional[int] = None
    pe_volume: Optional[int] = None
    pe_bid: Optional[float] = None
    pe_ask: Optional[float] = None
    pe_iv: Optional[float] = None
    pe_delta: Optional[float] = None
    pe_theta: Optional[float] = None
    pe_gamma: Optional[float] = None
    pe_vega: Optional[float] = None
    pe_source: str = "unknown"

    @property
    def total_oi(self) -> int:
        return (self.ce_oi or 0) + (self.pe_oi or 0)

    @property
    def pcr(self) -> Optional[float]:
        """Put-call ratio by OI at this strike."""
        if self.ce_oi and self.ce_oi > 0:
            return (self.pe_oi or 0) / self.ce_oi
        return None


@dataclass
class OptionChain:
    """Normalized option chain for an underlying + expiry."""

    underlying: str
    expiry: date
    spot_price: Optional[float] = None
    provider: str = "unknown"
    timestamp: Optional[datetime] = None
    strikes: list[OptionStrike] = field(default_factory=list)
    degraded: bool = False
    notes: list[str] = field(default_factory=list)

    # Analytics (populated by OptionChainAnalyzer)
    atm_strike: Optional[float] = None
    pcr_overall: Optional[float] = None
    max_pain: Optional[float] = None
    iv_skew: Optional[float] = None

    @property
    def sorted_strikes(self) -> list[OptionStrike]:
        return sorted(self.strikes, key=lambda s: s.strike)

    @property
    def call_oi_total(self) -> int:
        return sum(s.ce_oi or 0 for s in self.strikes)

    @property
    def put_oi_total(self) -> int:
        return sum(s.pe_oi or 0 for s in self.strikes)

    @property
    def chain_pcr(self) -> Optional[float]:
        """Overall put-call ratio by OI across all strikes."""
        total_ce = self.call_oi_total
        if total_ce > 0:
            return self.put_oi_total / total_ce
        return None

    def get_atm_strike(self) -> Optional[float]:
        """Return the strike closest to spot_price."""
        if not self.spot_price or not self.strikes:
            return None
        return min(
            (s.strike for s in self.strikes),
            key=lambda k: abs(k - self.spot_price),
        )

    def get_strikes_around_atm(self, n: int = 5) -> list[OptionStrike]:
        """Return n strikes above and below ATM."""
        atm = self.get_atm_strike()
        if atm is None:
            return self.sorted_strikes[: n * 2 + 1]
        sorted_s = self.sorted_strikes
        atm_idx = min(
            range(len(sorted_s)), key=lambda i: abs(sorted_s[i].strike - atm)
        )
        lo = max(0, atm_idx - n)
        hi = min(len(sorted_s), atm_idx + n + 1)
        return sorted_s[lo:hi]

    def to_dict(self) -> dict:
        """Serialize to dict."""
        return {
            "underlying": self.underlying,
            "expiry": str(self.expiry),
            "spot_price": self.spot_price,
            "provider": self.provider,
            "timestamp": str(self.timestamp) if self.timestamp else None,
            "degraded": self.degraded,
            "notes": self.notes,
            "chain_pcr": self.chain_pcr,
            "call_oi_total": self.call_oi_total,
            "put_oi_total": self.put_oi_total,
            "atm_strike": self.atm_strike or self.get_atm_strike(),
            "max_pain": self.max_pain,
            "iv_skew": self.iv_skew,
            "strike_count": len(self.strikes),
        }


class OptionChainBuilder:
    """Assembles normalized OptionChain objects from various data sources."""

    def from_dhan_response(
        self,
        underlying: str,
        expiry: date,
        dhan_chain: dict,
    ) -> OptionChain:
        """Build OptionChain from DhanHQDataSource.fetch_option_chain() response."""
        chain = OptionChain(
            underlying=underlying.upper(),
            expiry=expiry,
            provider="dhan",
            timestamp=datetime.utcnow(),
            degraded=dhan_chain.get("degraded", False),
        )

        # Build a strike map to merge CE and PE
        strike_map: dict[float, OptionStrike] = {}

        for call in dhan_chain.get("calls", []):
            s = float(call.get("strike", 0))
            if s not in strike_map:
                strike_map[s] = OptionStrike(strike=s)
            os = strike_map[s]
            os.ce_ltp = call.get("ltp")
            os.ce_oi = call.get("oi")
            os.ce_volume = call.get("volume")
            os.ce_bid = call.get("bid")
            os.ce_ask = call.get("ask")
            os.ce_iv = call.get("iv") or None
            os.ce_delta = call.get("delta") or None
            os.ce_theta = call.get("theta") or None
            os.ce_gamma = call.get("gamma") or None
            os.ce_vega = call.get("vega") or None
            os.ce_source = "dhan"

        for put in dhan_chain.get("puts", []):
            s = float(put.get("strike", 0))
            if s not in strike_map:
                strike_map[s] = OptionStrike(strike=s)
            os = strike_map[s]
            os.pe_ltp = put.get("ltp")
            os.pe_oi = put.get("oi")
            os.pe_volume = put.get("volume")
            os.pe_bid = put.get("bid")
            os.pe_ask = put.get("ask")
            os.pe_iv = put.get("iv") or None
            os.pe_delta = put.get("delta") or None
            os.pe_theta = put.get("theta") or None
            os.pe_gamma = put.get("gamma") or None
            os.pe_vega = put.get("vega") or None
            os.pe_source = "dhan"

        chain.strikes = list(strike_map.values())
        return chain

    def from_normalized_dict_list(
        self,
        underlying: str,
        expiry: date,
        rows: list[dict],
        provider: str = "generic",
    ) -> OptionChain:
        """Build OptionChain from a list of normalized dicts.

        Each dict should have: strike, option_type (CE/PE), and optionally
        ltp, oi, volume, bid, ask, iv, delta, theta, gamma, vega.
        """
        chain = OptionChain(
            underlying=underlying.upper(),
            expiry=expiry,
            provider=provider,
            timestamp=datetime.utcnow(),
        )
        strike_map: dict[float, OptionStrike] = {}

        for row in rows:
            s = float(row.get("strike", 0))
            otype = str(row.get("option_type", "")).upper()
            if s not in strike_map:
                strike_map[s] = OptionStrike(strike=s)
            os = strike_map[s]

            if otype in ("CE", "CALL"):
                os.ce_ltp = row.get("ltp")
                os.ce_oi = row.get("oi")
                os.ce_volume = row.get("volume")
                os.ce_bid = row.get("bid")
                os.ce_ask = row.get("ask")
                os.ce_iv = row.get("iv")
                os.ce_delta = row.get("delta")
                os.ce_theta = row.get("theta")
                os.ce_gamma = row.get("gamma")
                os.ce_vega = row.get("vega")
                os.ce_source = provider
            elif otype in ("PE", "PUT"):
                os.pe_ltp = row.get("ltp")
                os.pe_oi = row.get("oi")
                os.pe_volume = row.get("volume")
                os.pe_bid = row.get("bid")
                os.pe_ask = row.get("ask")
                os.pe_iv = row.get("iv")
                os.pe_delta = row.get("delta")
                os.pe_theta = row.get("theta")
                os.pe_gamma = row.get("gamma")
                os.pe_vega = row.get("vega")
                os.pe_source = provider

        chain.strikes = list(strike_map.values())
        return chain

    def from_instrument_registry(
        self,
        underlying: str,
        expiry: date,
        registry,
        provider: str = "registry",
    ) -> OptionChain:
        """Build OptionChain from InstrumentRegistry (no live quotes — structure only)."""
        options = registry.list_option_chain(underlying, expiry)
        chain = OptionChain(
            underlying=underlying.upper(),
            expiry=expiry,
            provider=provider,
            timestamp=datetime.utcnow(),
            notes=["structure_only_no_quotes"],
        )
        strike_map: dict[float, OptionStrike] = {}
        for inst in options:
            s = float(inst.strike or 0)
            if s not in strike_map:
                strike_map[s] = OptionStrike(strike=s)
            os = strike_map[s]
            from src.data.instrument_metadata import OptionType

            if inst.option_type == OptionType.CALL:
                os.ce_source = "registry"
            else:
                os.pe_source = "registry"
        chain.strikes = list(strike_map.values())
        return chain
