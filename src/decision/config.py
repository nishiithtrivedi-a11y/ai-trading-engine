"""
Configuration models for the Phase 5 decision/pick engine layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.decision.models import DecisionHorizon
from src.monitoring.models import RegimeState


def normalize_decision_horizon(value: DecisionHorizon | str) -> DecisionHorizon:
    if isinstance(value, DecisionHorizon):
        return value

    key = str(value).strip().lower()
    alias = {
        "intraday": DecisionHorizon.INTRADAY,
        "swing": DecisionHorizon.SWING,
        "positional": DecisionHorizon.POSITIONAL,
        "position": DecisionHorizon.POSITIONAL,
    }
    if key not in alias:
        raise ValueError(f"Unsupported decision horizon '{value}'")
    return alias[key]


def _normalize_weight_dict(weights: dict[str, float]) -> dict[str, float]:
    if not weights:
        raise ValueError("conviction weights cannot be empty")

    clean: dict[str, float] = {}
    for key, value in weights.items():
        w = float(value)
        if w < 0:
            raise ValueError("conviction weights cannot be negative")
        clean[str(key)] = w

    total = sum(clean.values())
    if total <= 0:
        raise ValueError("conviction weights total must be > 0")
    return {k: v / total for k, v in clean.items()}


@dataclass
class DecisionThresholdsConfig:
    min_score_by_horizon: dict[DecisionHorizon, float] = field(
        default_factory=lambda: {
            DecisionHorizon.INTRADAY: 60.0,
            DecisionHorizon.SWING: 65.0,
            DecisionHorizon.POSITIONAL: 70.0,
        }
    )
    min_rr_by_horizon: dict[DecisionHorizon, float] = field(
        default_factory=lambda: {
            DecisionHorizon.INTRADAY: 1.2,
            DecisionHorizon.SWING: 1.5,
            DecisionHorizon.POSITIONAL: 1.8,
        }
    )
    max_picks_by_horizon: dict[DecisionHorizon, int] = field(
        default_factory=lambda: {
            DecisionHorizon.INTRADAY: 5,
            DecisionHorizon.SWING: 5,
            DecisionHorizon.POSITIONAL: 5,
        }
    )
    max_picks_per_sector: int = 2
    max_correlated_picks: int = 2

    def __post_init__(self) -> None:
        self.min_score_by_horizon = {
            normalize_decision_horizon(k): float(v)
            for k, v in self.min_score_by_horizon.items()
        }
        self.min_rr_by_horizon = {
            normalize_decision_horizon(k): float(v)
            for k, v in self.min_rr_by_horizon.items()
        }
        self.max_picks_by_horizon = {
            normalize_decision_horizon(k): int(v)
            for k, v in self.max_picks_by_horizon.items()
        }

        for horizon in DecisionHorizon:
            if horizon not in self.min_score_by_horizon:
                raise ValueError(f"Missing min_score for horizon {horizon.value}")
            if horizon not in self.min_rr_by_horizon:
                raise ValueError(f"Missing min_rr for horizon {horizon.value}")
            if horizon not in self.max_picks_by_horizon:
                raise ValueError(f"Missing max_picks for horizon {horizon.value}")

            score = self.min_score_by_horizon[horizon]
            if not 0 <= score <= 100:
                raise ValueError(f"min_score for {horizon.value} must be in [0, 100]")

            rr = self.min_rr_by_horizon[horizon]
            if rr <= 0:
                raise ValueError(f"min_rr for {horizon.value} must be > 0")

            cap = self.max_picks_by_horizon[horizon]
            if cap < 0:
                raise ValueError(f"max_picks for {horizon.value} must be >= 0")

        if self.max_picks_per_sector < 1:
            raise ValueError("max_picks_per_sector must be >= 1")
        if self.max_correlated_picks < 1:
            raise ValueError("max_correlated_picks must be >= 1")

    def min_score(self, horizon: DecisionHorizon | str) -> float:
        return self.min_score_by_horizon[normalize_decision_horizon(horizon)]

    def min_rr(self, horizon: DecisionHorizon | str) -> float:
        return self.min_rr_by_horizon[normalize_decision_horizon(horizon)]

    def max_picks(self, horizon: DecisionHorizon | str) -> int:
        return self.max_picks_by_horizon[normalize_decision_horizon(horizon)]


@dataclass
class RegimePolicyConfig:
    allowed_regimes_by_horizon: dict[DecisionHorizon, set[RegimeState]] = field(
        default_factory=lambda: {
            DecisionHorizon.INTRADAY: {
                RegimeState.BULLISH,
                RegimeState.RANGEBOUND,
                RegimeState.HIGH_VOLATILITY,
                RegimeState.LOW_VOLATILITY,
                RegimeState.UNKNOWN,
            },
            DecisionHorizon.SWING: {
                RegimeState.BULLISH,
                RegimeState.RANGEBOUND,
                RegimeState.LOW_VOLATILITY,
                RegimeState.UNKNOWN,
            },
            DecisionHorizon.POSITIONAL: {
                RegimeState.BULLISH,
                RegimeState.LOW_VOLATILITY,
                RegimeState.UNKNOWN,
            },
        }
    )
    mismatch_penalty: float = 20.0
    hard_block_on_mismatch: bool = True
    high_volatility_extra_penalty: float = 10.0
    bearish_extra_penalty: float = 10.0

    def __post_init__(self) -> None:
        normalized: dict[DecisionHorizon, set[RegimeState]] = {}
        for raw_horizon, states in self.allowed_regimes_by_horizon.items():
            horizon = normalize_decision_horizon(raw_horizon)
            normalized[horizon] = {
                state if isinstance(state, RegimeState) else RegimeState(str(state))
                for state in states
            }
        self.allowed_regimes_by_horizon = normalized

        for horizon in DecisionHorizon:
            if horizon not in self.allowed_regimes_by_horizon:
                raise ValueError(f"Missing allowed regime policy for horizon {horizon.value}")

        if self.mismatch_penalty < 0:
            raise ValueError("mismatch_penalty must be >= 0")
        if self.high_volatility_extra_penalty < 0:
            raise ValueError("high_volatility_extra_penalty must be >= 0")
        if self.bearish_extra_penalty < 0:
            raise ValueError("bearish_extra_penalty must be >= 0")

    def allowed_for(self, horizon: DecisionHorizon | str) -> set[RegimeState]:
        return self.allowed_regimes_by_horizon[normalize_decision_horizon(horizon)]


@dataclass
class ConvictionWeightsConfig:
    weights: dict[str, float] = field(
        default_factory=lambda: {
            "scanner_score": 0.35,
            "setup_quality": 0.20,
            "risk_reward": 0.20,
            "regime_compatibility": 0.10,
            "relative_strength": 0.10,
            "liquidity": 0.03,
            "freshness": 0.02,
        }
    )

    def __post_init__(self) -> None:
        self.weights = _normalize_weight_dict(self.weights)


@dataclass
class SelectionPolicyConfig:
    enforce_unique_symbol: bool = True
    enforce_unique_symbol_timeframe_strategy: bool = True
    prefer_higher_rr_on_tie: bool = True
    stable_tie_breaker_keys: list[str] = field(
        default_factory=lambda: ["conviction_score", "risk_reward", "scanner_score", "symbol"]
    )


@dataclass
class DecisionExportConfig:
    output_dir: str = "output/decision"
    write_csv: bool = True
    write_json: bool = True
    intraday_csv_filename: str = "decision_top_intraday.csv"
    swing_csv_filename: str = "decision_top_swing.csv"
    positional_csv_filename: str = "decision_top_positional.csv"
    rejected_csv_filename: str = "decision_rejected.csv"
    summary_json_filename: str = "decision_summary.json"
    manifest_json_filename: str = "decision_manifest.json"

    def __post_init__(self) -> None:
        if not self.write_csv and not self.write_json:
            raise ValueError("At least one decision export format must be enabled")


@dataclass
class DecisionConfig:
    thresholds: DecisionThresholdsConfig = field(default_factory=DecisionThresholdsConfig)
    regime_policy: RegimePolicyConfig = field(default_factory=RegimePolicyConfig)
    conviction_weights: ConvictionWeightsConfig = field(default_factory=ConvictionWeightsConfig)
    selection_policy: SelectionPolicyConfig = field(default_factory=SelectionPolicyConfig)
    export: DecisionExportConfig = field(default_factory=DecisionExportConfig)
    include_rejections: bool = True
    continue_on_error: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
