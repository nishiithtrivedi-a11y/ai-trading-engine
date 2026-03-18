"""
Fundamental provider normalization and diagnostics helpers.

This module intentionally avoids hard dependency on any remote SDK. It
normalizes provider payloads when data is supplied by an upstream caller and
returns explicit degraded metadata when fields are unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

import pandas as pd


_FUNDAMENTAL_STALE_DAYS = 14


def _now_utc() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        clean = value.strip().replace(",", "")
        if not clean:
            return None
        value = clean
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(out):
        return None
    return out


def _to_timestamp(value: Any) -> pd.Timestamp | None:
    if value is None:
        return None
    try:
        ts = pd.Timestamp(value)
    except Exception:  # noqa: BLE001
        return None
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


def _candidate_sections(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    sections: list[Mapping[str, Any]] = [payload]
    for key in (
        "profile",
        "company_profile",
        "overview",
        "metrics",
        "ratios",
        "fundamentals",
        "valuation",
        "statement",
        "data",
    ):
        value = payload.get(key)
        if isinstance(value, Mapping):
            sections.append(value)
    return sections


def _pick_value(payload: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    for section in _candidate_sections(payload):
        for key in keys:
            if key in section and section.get(key) not in (None, ""):
                return section.get(key)
    return None


@dataclass(frozen=True)
class FundamentalEvent:
    event_type: str
    event_time: pd.Timestamp
    days_to_event: int | None
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FundamentalSnapshot:
    symbol: str
    company_name: str | None = None
    sector: str | None = None
    industry: str | None = None
    market_cap: float | None = None
    shares_outstanding: float | None = None
    eps: float | None = None
    pe: float | None = None
    pb: float | None = None
    debt_to_equity: float | None = None
    roe: float | None = None
    roa: float | None = None
    revenue_growth: float | None = None
    earnings_growth: float | None = None
    free_cash_flow: float | None = None
    fcf_yield: float | None = None
    operating_margin: float | None = None
    net_margin: float | None = None
    gross_margin: float | None = None
    dividend_yield: float | None = None
    earnings_time: pd.Timestamp | None = None
    provider: str = "none"
    fetched_at: pd.Timestamp = field(default_factory=_now_utc)
    as_of: pd.Timestamp | None = None
    stale: bool = False
    degraded: bool = True
    field_sources: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "company_name": self.company_name,
            "sector": self.sector,
            "industry": self.industry,
            "market_cap": self.market_cap,
            "shares_outstanding": self.shares_outstanding,
            "eps": self.eps,
            "pe": self.pe,
            "pb": self.pb,
            "debt_to_equity": self.debt_to_equity,
            "roe": self.roe,
            "roa": self.roa,
            "revenue_growth": self.revenue_growth,
            "earnings_growth": self.earnings_growth,
            "free_cash_flow": self.free_cash_flow,
            "fcf_yield": self.fcf_yield,
            "operating_margin": self.operating_margin,
            "net_margin": self.net_margin,
            "gross_margin": self.gross_margin,
            "dividend_yield": self.dividend_yield,
            "earnings_time": self.earnings_time.isoformat() if self.earnings_time else None,
            "provider": self.provider,
            "fetched_at": self.fetched_at.isoformat(),
            "as_of": self.as_of.isoformat() if self.as_of else None,
            "stale": self.stale,
            "degraded": self.degraded,
            "field_sources": dict(self.field_sources),
        }


@dataclass
class FundamentalDataBundle:
    snapshot: FundamentalSnapshot
    events: list[FundamentalEvent] = field(default_factory=list)
    provider_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot": self.snapshot.to_dict(),
            "events": [
                {
                    "event_type": event.event_type,
                    "event_time": event.event_time.isoformat(),
                    "days_to_event": event.days_to_event,
                    "source": event.source,
                    "metadata": dict(event.metadata),
                }
                for event in self.events
            ],
            "provider_metadata": dict(self.provider_metadata),
        }


def normalize_fundamental_payload(
    provider_name: str,
    symbol: str,
    payload: Mapping[str, Any] | None,
    *,
    as_of: pd.Timestamp | None = None,
) -> FundamentalDataBundle:
    clean_provider = str(provider_name or "none").strip().lower() or "none"
    clean_symbol = str(symbol).strip().upper()
    fetched_at = _now_utc()
    ref_as_of = as_of.tz_convert("UTC") if as_of is not None and as_of.tzinfo else as_of

    if ref_as_of is None:
        inferred_as_of = _to_timestamp(
            _pick_value(payload or {}, ("as_of", "updated_at", "report_date", "latest_update"))
        )
        ref_as_of = inferred_as_of or fetched_at

    if payload is None:
        snapshot = FundamentalSnapshot(
            symbol=clean_symbol,
            provider=clean_provider,
            fetched_at=fetched_at,
            as_of=ref_as_of,
            stale=False,
            degraded=True,
            field_sources={},
        )
        return FundamentalDataBundle(
            snapshot=snapshot,
            events=[],
            provider_metadata={
                "provider": clean_provider,
                "configured": clean_provider != "none",
                "available": False,
                "degraded": True,
                "reason": "no_payload",
            },
        )

    raw_company_name = _pick_value(payload, ("company_name", "companyName", "name", "shortName"))
    raw_sector = _pick_value(payload, ("sector", "gics_sector", "sector_name"))
    raw_industry = _pick_value(payload, ("industry", "gics_industry", "industry_name"))
    raw_market_cap = _pick_value(payload, ("market_cap", "marketCap", "marketCapitalization"))
    raw_shares = _pick_value(payload, ("shares_outstanding", "sharesOutstanding"))
    raw_eps = _pick_value(payload, ("eps", "EPS", "epsTTM"))
    raw_pe = _pick_value(payload, ("pe", "pe_ratio", "PERatio", "peTTM"))
    raw_pb = _pick_value(payload, ("pb", "pb_ratio", "priceToBookRatio"))
    raw_de = _pick_value(payload, ("debt_to_equity", "debtEquity", "debtToEquity"))
    raw_roe = _pick_value(payload, ("roe", "returnOnEquity", "returnOnEquityTTM"))
    raw_roa = _pick_value(payload, ("roa", "returnOnAssets", "returnOnAssetsTTM"))
    raw_rev_growth = _pick_value(payload, ("revenue_growth", "revenueGrowth", "revenueGrowthTTM"))
    raw_earn_growth = _pick_value(payload, ("earnings_growth", "earningsGrowth", "earningsGrowthTTM"))
    raw_fcf = _pick_value(payload, ("free_cash_flow", "freeCashFlow", "freeCashflow"))
    raw_fcf_yield = _pick_value(payload, ("fcf_yield", "freeCashFlowYield", "fcfYield"))
    raw_op_margin = _pick_value(payload, ("operating_margin", "operatingMargin", "operatingMarginsTTM"))
    raw_net_margin = _pick_value(payload, ("net_margin", "netMargin", "profitMargin", "netProfitMargin"))
    raw_gross_margin = _pick_value(payload, ("gross_margin", "grossMargin", "grossProfitMargin"))
    raw_div_yield = _pick_value(payload, ("dividend_yield", "dividendYield", "forwardAnnualDividendYield"))
    raw_earnings_time = _pick_value(
        payload,
        ("earnings_time", "earnings_date", "nextEarningsDate", "earningsAnnouncement"),
    )

    market_cap = _to_float(raw_market_cap)
    free_cash_flow = _to_float(raw_fcf)
    derived_fcf_yield = None
    if market_cap and market_cap > 0 and free_cash_flow is not None:
        derived_fcf_yield = (free_cash_flow / market_cap) * 100.0

    fcf_yield = _to_float(raw_fcf_yield)
    field_sources: dict[str, str] = {}
    if fcf_yield is None and derived_fcf_yield is not None:
        fcf_yield = derived_fcf_yield
        field_sources["fcf_yield"] = "derived"
    elif fcf_yield is not None:
        field_sources["fcf_yield"] = "provider"

    field_map: dict[str, Any] = {
        "company_name": raw_company_name,
        "sector": raw_sector,
        "industry": raw_industry,
        "market_cap": market_cap,
        "shares_outstanding": _to_float(raw_shares),
        "eps": _to_float(raw_eps),
        "pe": _to_float(raw_pe),
        "pb": _to_float(raw_pb),
        "debt_to_equity": _to_float(raw_de),
        "roe": _to_float(raw_roe),
        "roa": _to_float(raw_roa),
        "revenue_growth": _to_float(raw_rev_growth),
        "earnings_growth": _to_float(raw_earn_growth),
        "free_cash_flow": free_cash_flow,
        "fcf_yield": fcf_yield,
        "operating_margin": _to_float(raw_op_margin),
        "net_margin": _to_float(raw_net_margin),
        "gross_margin": _to_float(raw_gross_margin),
        "dividend_yield": _to_float(raw_div_yield),
        "earnings_time": _to_timestamp(raw_earnings_time),
    }

    for field_name, value in field_map.items():
        if field_name in field_sources:
            continue
        field_sources[field_name] = "provider" if value is not None else "missing"

    stale = bool(
        ref_as_of is not None and (fetched_at - ref_as_of).days > _FUNDAMENTAL_STALE_DAYS
    )
    available_fields = sum(1 for value in field_map.values() if value is not None)
    degraded = available_fields < 5

    snapshot = FundamentalSnapshot(
        symbol=clean_symbol,
        company_name=str(field_map["company_name"]).strip() if field_map["company_name"] else None,
        sector=str(field_map["sector"]).strip() if field_map["sector"] else None,
        industry=str(field_map["industry"]).strip() if field_map["industry"] else None,
        market_cap=field_map["market_cap"],
        shares_outstanding=field_map["shares_outstanding"],
        eps=field_map["eps"],
        pe=field_map["pe"],
        pb=field_map["pb"],
        debt_to_equity=field_map["debt_to_equity"],
        roe=field_map["roe"],
        roa=field_map["roa"],
        revenue_growth=field_map["revenue_growth"],
        earnings_growth=field_map["earnings_growth"],
        free_cash_flow=field_map["free_cash_flow"],
        fcf_yield=field_map["fcf_yield"],
        operating_margin=field_map["operating_margin"],
        net_margin=field_map["net_margin"],
        gross_margin=field_map["gross_margin"],
        dividend_yield=field_map["dividend_yield"],
        earnings_time=field_map["earnings_time"],
        provider=clean_provider,
        fetched_at=fetched_at,
        as_of=ref_as_of,
        stale=stale,
        degraded=degraded,
        field_sources=field_sources,
    )

    events: list[FundamentalEvent] = []
    if snapshot.earnings_time is not None:
        delta = snapshot.earnings_time - fetched_at
        days_to_event = int(delta.total_seconds() // 86400) if delta.total_seconds() >= 0 else None
        events.append(
            FundamentalEvent(
                event_type="earnings",
                event_time=snapshot.earnings_time,
                days_to_event=days_to_event,
                source=clean_provider,
                metadata={"symbol": clean_symbol},
            )
        )

    return FundamentalDataBundle(
        snapshot=snapshot,
        events=events,
        provider_metadata={
            "provider": clean_provider,
            "configured": clean_provider != "none",
            "available": True,
            "degraded": degraded,
            "stale": stale,
            "freshness_days": int((fetched_at - ref_as_of).days) if ref_as_of is not None else None,
            "field_coverage": {
                "available_fields": available_fields,
                "total_fields": len(field_map),
            },
        },
    )
