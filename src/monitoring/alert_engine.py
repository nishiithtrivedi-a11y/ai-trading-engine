"""
Structured alert generation for Phase 4 monitoring.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from src.monitoring.config import AlertEngineConfig
from src.monitoring.models import (
    Alert,
    AlertSeverity,
    RegimeAssessment,
    RegimeState,
    RelativeStrengthSnapshot,
    Watchlist,
)
from src.scanners.models import Opportunity, ScanResult


class AlertEngineError(Exception):
    """Raised when alert generation fails."""


@dataclass
class AlertEngine:
    dedupe_state: dict[str, pd.Timestamp] = field(default_factory=dict)

    def generate(
        self,
        scan_result: Optional[ScanResult],
        config: AlertEngineConfig,
        regime_assessment: Optional[RegimeAssessment] = None,
        previous_regime: Optional[RegimeState] = None,
        relative_strength: Optional[list[RelativeStrengthSnapshot]] = None,
        watchlists: Optional[dict[str, Watchlist]] = None,
        now: Optional[pd.Timestamp] = None,
    ) -> list[Alert]:
        if not config.enabled:
            return []

        current_time = now or pd.Timestamp.now(tz="UTC")
        alerts: list[Alert] = []

        if scan_result is not None:
            alerts.extend(
                self._opportunity_alerts(
                    opportunities=scan_result.opportunities,
                    config=config,
                    watchlists=watchlists or {},
                    now=current_time,
                )
            )

        if config.include_regime_change_alerts and regime_assessment is not None and previous_regime is not None:
            if regime_assessment.regime != previous_regime:
                severity = (
                    AlertSeverity.WARNING
                    if regime_assessment.regime in {RegimeState.BEARISH, RegimeState.HIGH_VOLATILITY}
                    else AlertSeverity.INFO
                )
                alerts.append(
                    Alert(
                        rule_id="regime_change",
                        title="Market regime changed",
                        message=(
                            f"Regime changed from {previous_regime.value} "
                            f"to {regime_assessment.regime.value}"
                        ),
                        severity=severity,
                        timestamp=current_time,
                        metadata={"from": previous_regime.value, "to": regime_assessment.regime.value},
                    )
                )

        if config.include_relative_strength_alerts and relative_strength:
            top_rows = [row for row in relative_strength if row.rank and row.rank <= config.relative_strength_top_n]
            for row in top_rows:
                alerts.append(
                    Alert(
                        rule_id="relative_strength_top_rank",
                        symbol=row.symbol,
                        title="Relative strength leader",
                        message=f"{row.symbol} entered top {config.relative_strength_top_n} RS ranks",
                        severity=AlertSeverity.INFO,
                        timestamp=current_time,
                        metadata={"rank": row.rank, "score": row.score},
                    )
                )

        return self._dedupe(alerts, config.dedupe_window_minutes, current_time)

    def _opportunity_alerts(
        self,
        opportunities: list[Opportunity],
        config: AlertEngineConfig,
        watchlists: dict[str, Watchlist],
        now: pd.Timestamp,
    ) -> list[Alert]:
        alerts: list[Alert] = []
        watchlist_map = self._build_watchlist_symbol_map(watchlists)

        for opp in opportunities:
            if float(opp.score) < config.min_opportunity_score:
                continue

            watchlist_names = watchlist_map.get(opp.symbol, [])
            if config.include_watchlist_actionable_alerts and watchlists and not watchlist_names:
                continue

            severity = (
                AlertSeverity.HIGH_PRIORITY
                if float(opp.score) >= config.high_priority_score
                else AlertSeverity.WARNING
            )

            alerts.append(
                Alert(
                    rule_id="new_actionable_opportunity",
                    symbol=opp.symbol,
                    title="Actionable opportunity",
                    message=(
                        f"{opp.symbol} {opp.timeframe} {opp.strategy_name} "
                        f"score={opp.score:.2f} entry={opp.entry_price:.2f}"
                    ),
                    severity=severity,
                    timestamp=now,
                    metadata={
                        "score": float(opp.score),
                        "timeframe": opp.timeframe,
                        "strategy_name": opp.strategy_name,
                        "watchlists": watchlist_names,
                    },
                )
            )

        return alerts

    @staticmethod
    def _build_watchlist_symbol_map(watchlists: dict[str, Watchlist]) -> dict[str, list[str]]:
        mapping: dict[str, list[str]] = {}
        for watchlist_name, watchlist in watchlists.items():
            for symbol in watchlist.symbols:
                mapping.setdefault(symbol, [])
                if watchlist_name not in mapping[symbol]:
                    mapping[symbol].append(watchlist_name)
        return mapping

    def _dedupe(
        self,
        alerts: list[Alert],
        dedupe_window_minutes: int,
        now: pd.Timestamp,
    ) -> list[Alert]:
        if dedupe_window_minutes <= 0:
            for alert in alerts:
                self.dedupe_state[alert.dedupe_key or alert.alert_id] = now
            return alerts

        allowed: list[Alert] = []
        window = pd.Timedelta(minutes=dedupe_window_minutes)
        for alert in alerts:
            key = alert.dedupe_key or alert.alert_id
            last_ts = self.dedupe_state.get(key)
            if last_ts is not None and (now - last_ts) < window:
                continue
            self.dedupe_state[key] = now
            allowed.append(alert)
        return allowed
