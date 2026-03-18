"""
Options analytics — Black-Scholes Greeks, IV, chain-level metrics.

All computations use pure Python + math stdlib (no scipy dependency).
Computed values are clearly distinguished from provider-supplied values.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from src.analysis.derivatives.options.chain import OptionChain, OptionStrike


# ---------------------------------------------------------------------------
# Black-Scholes implementation (pure Python)
# ---------------------------------------------------------------------------


def _norm_cdf(x: float) -> float:
    """Standard normal CDF using error function approximation."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    """Standard normal PDF."""
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


@dataclass
class BSMResult:
    """Black-Scholes-Merton computed option values."""

    option_type: str          # "CE" or "PE"
    theoretical_price: float
    delta: float
    gamma: float
    theta: float              # per calendar day
    vega: float               # per 1% change in vol
    rho: float
    d1: float
    d2: float
    iv_used: float            # annualized volatility used
    computed: bool = True     # always True — indicates computed (not provider-supplied)


def black_scholes(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: str = "CE",
) -> BSMResult:
    """Compute Black-Scholes option price and Greeks.

    Args:
        S: Spot/futures price.
        K: Strike price.
        T: Time to expiry in years (e.g., 7/365 for 7 days).
        r: Risk-free rate (use India 10Y gsec rate, ~0.065).
        sigma: Annualized volatility (e.g., 0.15 for 15% vol).
        option_type: "CE" for call, "PE" for put.

    Returns:
        BSMResult with price and Greeks.

    Raises:
        ValueError: If inputs are invalid (T <= 0, S <= 0, K <= 0, sigma <= 0).
    """
    if T <= 0:
        raise ValueError(f"Time to expiry T must be > 0, got {T}")
    if S <= 0 or K <= 0:
        raise ValueError(f"S and K must be > 0, got S={S}, K={K}")
    if sigma <= 0:
        raise ValueError(f"Volatility sigma must be > 0, got {sigma}")

    sqrt_T = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T

    disc = math.exp(-r * T)

    if option_type.upper() in ("CE", "CALL"):
        price = S * _norm_cdf(d1) - K * disc * _norm_cdf(d2)
        delta = _norm_cdf(d1)
        theta = (
            -S * _norm_pdf(d1) * sigma / (2 * sqrt_T)
            - r * K * disc * _norm_cdf(d2)
        ) / 365
        rho = K * T * disc * _norm_cdf(d2) / 100
    else:  # PE / PUT
        price = K * disc * _norm_cdf(-d2) - S * _norm_cdf(-d1)
        delta = _norm_cdf(d1) - 1.0
        theta = (
            -S * _norm_pdf(d1) * sigma / (2 * sqrt_T)
            + r * K * disc * _norm_cdf(-d2)
        ) / 365
        rho = -K * T * disc * _norm_cdf(-d2) / 100

    gamma = _norm_pdf(d1) / (S * sigma * sqrt_T)
    vega = S * _norm_pdf(d1) * sqrt_T / 100

    return BSMResult(
        option_type=option_type.upper(),
        theoretical_price=max(0.0, price),
        delta=delta,
        gamma=gamma,
        theta=theta,
        vega=vega,
        rho=rho,
        d1=d1,
        d2=d2,
        iv_used=sigma,
        computed=True,
    )


def implied_volatility(
    market_price: float,
    S: float,
    K: float,
    T: float,
    r: float,
    option_type: str = "CE",
    max_iterations: int = 100,
    tolerance: float = 1e-6,
) -> Optional[float]:
    """Compute implied volatility using bisection method.

    Args:
        market_price: Observed market price of the option.
        S, K, T, r: Black-Scholes parameters (see black_scholes()).
        option_type: "CE" or "PE".
        max_iterations: Max bisection iterations.
        tolerance: Convergence tolerance.

    Returns:
        Annualized implied volatility as a decimal (e.g., 0.15 for 15%).
        None if computation fails or inputs are invalid.
    """
    if market_price <= 0 or T <= 0 or S <= 0 or K <= 0:
        return None

    # Intrinsic value bounds check
    if option_type.upper() in ("CE", "CALL"):
        intrinsic = max(0.0, S - K * math.exp(-r * T))
    else:
        intrinsic = max(0.0, K * math.exp(-r * T) - S)

    if market_price < intrinsic:
        return None  # price below intrinsic — no valid IV

    # Bisection: sigma in [1e-6, 5.0] (0.0001% to 500% annualized vol)
    lo, hi = 1e-6, 5.0

    for _ in range(max_iterations):
        mid = (lo + hi) / 2.0
        try:
            result = black_scholes(S, K, T, r, mid, option_type)
            diff = result.theoretical_price - market_price
        except (ValueError, ZeroDivisionError):
            return None

        if abs(diff) < tolerance:
            return mid
        if diff > 0:
            hi = mid
        else:
            lo = mid

    return (lo + hi) / 2.0


# ---------------------------------------------------------------------------
# Moneyness classification
# ---------------------------------------------------------------------------


def classify_moneyness(
    spot: float,
    strike: float,
    option_type: str,
    threshold_pct: float = 0.02,
) -> str:
    """Classify option as ATM, ITM, or OTM.

    Args:
        spot: Current spot/futures price.
        strike: Option strike price.
        option_type: "CE" or "PE".
        threshold_pct: Distance from ATM to still be considered ATM (default 2%).

    Returns:
        "ATM", "ITM", or "OTM"
    """
    if spot <= 0:
        return "UNKNOWN"
    dist_pct = abs(strike - spot) / spot
    if dist_pct <= threshold_pct:
        return "ATM"
    if option_type.upper() in ("CE", "CALL"):
        return "ITM" if strike < spot else "OTM"
    else:
        return "ITM" if strike > spot else "OTM"


# ---------------------------------------------------------------------------
# Chain-level analytics
# ---------------------------------------------------------------------------


@dataclass
class ChainAnalytics:
    """Chain-level analytics derived from an OptionChain."""

    underlying: str
    expiry: str
    spot_price: Optional[float]
    atm_strike: Optional[float]
    pcr_overall: float               # put-call ratio by OI
    max_pain: Optional[float]
    iv_skew: Optional[float]         # OTM put IV minus OTM call IV
    call_oi_total: int
    put_oi_total: int
    highest_oi_call_strike: Optional[float]
    highest_oi_put_strike: Optional[float]
    call_resistance: Optional[float]  # strike with highest call OI (resistance)
    put_support: Optional[float]      # strike with highest put OI (support)
    chain_breadth: int                # number of strikes with both CE+PE data
    has_computed_greeks: bool = False
    notes: list[str] = None

    def __post_init__(self):
        if self.notes is None:
            self.notes = []


class OptionChainAnalyzer:
    """Compute chain-level analytics from an OptionChain."""

    def __init__(self, risk_free_rate: float = 0.065):
        """Args:
            risk_free_rate: India risk-free rate (default ~6.5% for 10Y gsec).
        """
        self._r = risk_free_rate

    def analyze(self, chain: OptionChain) -> ChainAnalytics:
        """Compute all analytics for a chain."""
        atm = chain.get_atm_strike()
        pcr = chain.chain_pcr or 0.0

        # Max pain
        max_pain = self._compute_max_pain(chain)

        # OI concentration
        call_oi_by_strike = {
            s.strike: (s.ce_oi or 0) for s in chain.strikes if s.ce_oi
        }
        put_oi_by_strike = {
            s.strike: (s.pe_oi or 0) for s in chain.strikes if s.pe_oi
        }

        highest_oi_call = (
            max(call_oi_by_strike, key=call_oi_by_strike.get)
            if call_oi_by_strike
            else None
        )
        highest_oi_put = (
            max(put_oi_by_strike, key=put_oi_by_strike.get)
            if put_oi_by_strike
            else None
        )

        # IV skew (OTM put IV minus OTM call IV)
        iv_skew = self._compute_iv_skew(chain, atm)

        # Chain breadth
        breadth = sum(
            1
            for s in chain.strikes
            if s.ce_ltp is not None and s.pe_ltp is not None
        )

        return ChainAnalytics(
            underlying=chain.underlying,
            expiry=str(chain.expiry),
            spot_price=chain.spot_price,
            atm_strike=atm,
            pcr_overall=pcr,
            max_pain=max_pain,
            iv_skew=iv_skew,
            call_oi_total=chain.call_oi_total,
            put_oi_total=chain.put_oi_total,
            highest_oi_call_strike=highest_oi_call,
            highest_oi_put_strike=highest_oi_put,
            call_resistance=highest_oi_call,
            put_support=highest_oi_put,
            chain_breadth=breadth,
        )

    def enrich_greeks(self, chain: OptionChain, T: float) -> OptionChain:
        """Compute BSM Greeks for strikes missing provider-supplied values.

        Modifies chain.strikes in-place. T is time to expiry in years.
        Only enriches where spot_price is available and T > 0.
        """
        if not chain.spot_price or T <= 0:
            chain.notes.append("greeks_not_computed: missing spot or T <= 0")
            return chain

        spot = chain.spot_price
        r = self._r

        for strike in chain.strikes:
            k = strike.strike
            if k <= 0:
                continue

            # Call side
            if strike.ce_ltp is not None and strike.ce_iv is None:
                iv = implied_volatility(strike.ce_ltp, spot, k, T, r, "CE")
                if iv is not None:
                    strike.ce_iv = iv
                    try:
                        bsm = black_scholes(spot, k, T, r, iv, "CE")
                        if strike.ce_delta is None:
                            strike.ce_delta = bsm.delta
                        if strike.ce_gamma is None:
                            strike.ce_gamma = bsm.gamma
                        if strike.ce_theta is None:
                            strike.ce_theta = bsm.theta
                        if strike.ce_vega is None:
                            strike.ce_vega = bsm.vega
                    except ValueError:
                        pass

            # Put side
            if strike.pe_ltp is not None and strike.pe_iv is None:
                iv = implied_volatility(strike.pe_ltp, spot, k, T, r, "PE")
                if iv is not None:
                    strike.pe_iv = iv
                    try:
                        bsm = black_scholes(spot, k, T, r, iv, "PE")
                        if strike.pe_delta is None:
                            strike.pe_delta = bsm.delta
                        if strike.pe_gamma is None:
                            strike.pe_gamma = bsm.gamma
                        if strike.pe_theta is None:
                            strike.pe_theta = bsm.theta
                        if strike.pe_vega is None:
                            strike.pe_vega = bsm.vega
                    except ValueError:
                        pass

        return chain

    def _compute_max_pain(self, chain: OptionChain) -> Optional[float]:
        """Compute max pain strike — strike that causes maximum loss to option buyers."""
        strikes_with_data = [s for s in chain.strikes if s.total_oi > 0]
        if not strikes_with_data:
            return None

        min_pain = float("inf")
        max_pain_strike = None

        for candidate in strikes_with_data:
            k = candidate.strike
            pain = 0.0
            for s in strikes_with_data:
                # Call writers: lose (S - K) for each call ITM above candidate
                if s.strike > k and s.ce_oi:
                    pain += s.ce_oi * (s.strike - k)
                # Put writers: lose (K - S) for each put ITM below candidate
                if s.strike < k and s.pe_oi:
                    pain += s.pe_oi * (k - s.strike)
            if pain < min_pain:
                min_pain = pain
                max_pain_strike = k

        return max_pain_strike

    def _compute_iv_skew(
        self, chain: OptionChain, atm_strike: Optional[float]
    ) -> Optional[float]:
        """Compute IV skew as OTM put IV minus OTM call IV near ATM."""
        if atm_strike is None:
            return None

        sorted_s = chain.sorted_strikes
        atm_idx = None
        for i, s in enumerate(sorted_s):
            if s.strike == atm_strike:
                atm_idx = i
                break

        if atm_idx is None:
            return None

        # Get first OTM put (below ATM) and first OTM call (above ATM)
        otm_put_iv = None
        for i in range(atm_idx - 1, -1, -1):
            if sorted_s[i].pe_iv is not None:
                otm_put_iv = sorted_s[i].pe_iv
                break

        otm_call_iv = None
        for i in range(atm_idx + 1, len(sorted_s)):
            if sorted_s[i].ce_iv is not None:
                otm_call_iv = sorted_s[i].ce_iv
                break

        if otm_put_iv is not None and otm_call_iv is not None:
            return otm_put_iv - otm_call_iv
        return None

    def compute_strike_ladder(
        self,
        chain: OptionChain,
        spot: float,
        n_strikes: int = 5,
        step: Optional[float] = None,
    ) -> list[float]:
        """Build a strike ladder of n strikes above and below spot.

        If step is None, infers step from existing strikes.
        """
        if not chain.strikes:
            return []

        existing = sorted(s.strike for s in chain.strikes)

        if step is None and len(existing) > 1:
            # Infer step from most common gap
            gaps = [existing[i + 1] - existing[i] for i in range(len(existing) - 1)]
            step = sorted(gaps)[len(gaps) // 2]  # median gap

        if step is None or step <= 0:
            return existing[: n_strikes * 2 + 1]

        # ATM strike (round to nearest step)
        atm = round(spot / step) * step
        return [atm + i * step for i in range(-n_strikes, n_strikes + 1)]
