"""
Tests for src/risk/risk_engine.py  (Phase 6 -- Risk Engine).

Covers:
  - PortfolioRiskConfig default values and validation
  - PositionSizer.size_position() and max_capital_for_risk()
  - RiskDecision dataclass
  - PortfolioRiskManager.check_entry() - all three rule paths
  - PortfolioRiskManager.compute_position_size()
  - PortfolioRiskManager.compute_drawdown()
  - Regime-aware throttling in check_entry()
  - validate_portfolio_risk() with clean / violating equity curves
  - generate_risk_report() output and file writing
  - src/risk/__init__.py public exports
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------
from src.risk.risk_engine import (
    PortfolioRiskConfig,
    PortfolioRiskManager,
    PositionSizer,
    RiskDecision,
    generate_risk_report,
    validate_portfolio_risk,
)


# ===========================================================================
# Helpers
# ===========================================================================

def _make_equity_series(values: list[float]) -> pd.Series:
    return pd.Series(values, dtype=float)


def _make_equity_curve(values: list[float], col: str = "portfolio_equity") -> pd.DataFrame:
    return pd.DataFrame({col: values}, dtype=float)


# ===========================================================================
# 1. PortfolioRiskConfig
# ===========================================================================

class TestPortfolioRiskConfig:
    """Tests for PortfolioRiskConfig defaults and structure."""

    def test_default_values(self):
        cfg = PortfolioRiskConfig()
        assert cfg.max_risk_per_trade_pct == pytest.approx(0.01)
        assert cfg.max_portfolio_exposure_pct == pytest.approx(0.20)
        assert cfg.max_drawdown_pct == pytest.approx(0.15)
        assert cfg.max_concurrent_positions == 10

    def test_custom_values(self):
        cfg = PortfolioRiskConfig(
            max_risk_per_trade_pct=0.02,
            max_portfolio_exposure_pct=0.30,
            max_drawdown_pct=0.10,
            max_concurrent_positions=5,
        )
        assert cfg.max_risk_per_trade_pct == pytest.approx(0.02)
        assert cfg.max_portfolio_exposure_pct == pytest.approx(0.30)
        assert cfg.max_drawdown_pct == pytest.approx(0.10)
        assert cfg.max_concurrent_positions == 5

    def test_regime_overrides_default_empty(self):
        cfg = PortfolioRiskConfig()
        assert isinstance(cfg.regime_risk_overrides, dict)
        assert len(cfg.regime_risk_overrides) == 0

    def test_regime_overrides_custom(self):
        overrides = {
            "risk_off": {"max_portfolio_exposure_pct": 0.00, "max_concurrent_positions": 0},
            "bearish_volatile": {"max_portfolio_exposure_pct": 0.05},
        }
        cfg = PortfolioRiskConfig(regime_risk_overrides=overrides)
        assert "risk_off" in cfg.regime_risk_overrides
        assert "bearish_volatile" in cfg.regime_risk_overrides

    def test_config_attributes_accessible(self):
        cfg = PortfolioRiskConfig()
        # All four primary fields must be accessible attributes
        assert hasattr(cfg, "max_risk_per_trade_pct")
        assert hasattr(cfg, "max_portfolio_exposure_pct")
        assert hasattr(cfg, "max_drawdown_pct")
        assert hasattr(cfg, "max_concurrent_positions")
        assert hasattr(cfg, "regime_risk_overrides")


# ===========================================================================
# 2. PositionSizer
# ===========================================================================

class TestPositionSizer:
    """Tests for PositionSizer.size_position() and max_capital_for_risk()."""

    def test_default_position_size_pct(self):
        sizer = PositionSizer()
        assert sizer.position_size_pct == pytest.approx(0.95)

    def test_size_position_basic(self):
        sizer = PositionSizer(position_size_pct=1.0)
        qty = sizer.size_position(capital=10_000.0, price=100.0)
        assert qty == pytest.approx(100.0)

    def test_size_position_with_pct(self):
        sizer = PositionSizer(position_size_pct=0.95)
        qty = sizer.size_position(capital=10_000.0, price=100.0)
        # 10000 * 0.95 / 100 = 95
        assert qty == pytest.approx(95.0)

    def test_size_position_zero_price(self):
        sizer = PositionSizer()
        qty = sizer.size_position(capital=10_000.0, price=0.0)
        assert qty == 0.0

    def test_size_position_zero_capital(self):
        sizer = PositionSizer()
        qty = sizer.size_position(capital=0.0, price=100.0)
        assert qty == 0.0

    def test_size_position_negative_price(self):
        sizer = PositionSizer()
        qty = sizer.size_position(capital=10_000.0, price=-50.0)
        assert qty == 0.0

    def test_size_position_negative_capital(self):
        sizer = PositionSizer()
        qty = sizer.size_position(capital=-1000.0, price=50.0)
        assert qty == 0.0

    def test_size_position_pct_clamped_above_one(self):
        sizer = PositionSizer(position_size_pct=2.0)  # over 100% - clamped to 1
        qty = sizer.size_position(capital=1_000.0, price=10.0)
        assert qty == pytest.approx(100.0)

    def test_size_position_pct_clamped_below_zero(self):
        sizer = PositionSizer(position_size_pct=-0.5)  # negative - clamped to 0
        qty = sizer.size_position(capital=1_000.0, price=10.0)
        assert qty == pytest.approx(0.0)

    def test_max_capital_for_risk_basic(self):
        sizer = PositionSizer()
        # 100_000 equity * 1% risk / 2% stop = 50_000 max capital
        cap = sizer.max_capital_for_risk(
            portfolio_equity=100_000.0, stop_loss_pct=0.02, max_risk_pct=0.01
        )
        assert cap == pytest.approx(50_000.0)

    def test_max_capital_for_risk_zero_stop(self):
        sizer = PositionSizer()
        cap = sizer.max_capital_for_risk(portfolio_equity=100_000.0, stop_loss_pct=0.0)
        assert cap == 0.0

    def test_max_capital_for_risk_zero_equity(self):
        sizer = PositionSizer()
        cap = sizer.max_capital_for_risk(portfolio_equity=0.0, stop_loss_pct=0.02)
        assert cap == 0.0

    def test_max_capital_for_risk_tight_stop(self):
        sizer = PositionSizer()
        # 1% risk / 5% stop = 20% of equity
        cap = sizer.max_capital_for_risk(
            portfolio_equity=10_000.0, stop_loss_pct=0.05, max_risk_pct=0.01
        )
        assert cap == pytest.approx(2_000.0)


# ===========================================================================
# 3. RiskDecision
# ===========================================================================

class TestRiskDecision:
    """Tests for the RiskDecision dataclass."""

    def test_allowed_default(self):
        rd = RiskDecision(allowed=True)
        assert rd.allowed is True
        assert rd.blocked_reason == ""
        assert rd.regime_throttled is False

    def test_blocked_with_reason(self):
        rd = RiskDecision(allowed=False, blocked_reason="Drawdown kill-switch triggered")
        assert rd.allowed is False
        assert "Drawdown" in rd.blocked_reason

    def test_regime_throttled_flag(self):
        rd = RiskDecision(allowed=False, regime_throttled=True, blocked_reason="positions capped")
        assert rd.regime_throttled is True

    def test_effective_fields(self):
        rd = RiskDecision(
            allowed=True,
            effective_max_exposure_pct=0.10,
            effective_max_positions=5,
        )
        assert rd.effective_max_exposure_pct == pytest.approx(0.10)
        assert rd.effective_max_positions == 5


# ===========================================================================
# 4. PortfolioRiskManager.check_entry()
# ===========================================================================

class TestPortfolioRiskManagerCheckEntry:
    """Tests for the pre-trade entry gate."""

    def _mgr(self, **kwargs) -> PortfolioRiskManager:
        cfg = PortfolioRiskConfig(**kwargs)
        return PortfolioRiskManager(config=cfg)

    # --- Happy path ---

    def test_check_entry_allowed_clean(self):
        mgr = self._mgr()
        decision = mgr.check_entry(
            portfolio_equity=100_000.0,
            current_drawdown_pct=0.0,
            open_positions_count=0,
            deployed_capital=0.0,
        )
        assert decision.allowed is True
        assert decision.blocked_reason == ""

    def test_check_entry_allowed_partial_positions(self):
        mgr = self._mgr(max_concurrent_positions=10, max_portfolio_exposure_pct=0.50)
        decision = mgr.check_entry(
            portfolio_equity=100_000.0,
            current_drawdown_pct=0.05,
            open_positions_count=5,
            deployed_capital=20_000.0,
        )
        assert decision.allowed is True

    # --- Rule 1: Drawdown kill-switch ---

    def test_check_entry_blocked_drawdown(self):
        mgr = self._mgr(max_drawdown_pct=0.15)
        decision = mgr.check_entry(
            portfolio_equity=85_000.0,
            current_drawdown_pct=0.16,   # > 0.15 limit
            open_positions_count=0,
            deployed_capital=0.0,
        )
        assert decision.allowed is False
        assert "drawdown" in decision.blocked_reason.lower() or "kill" in decision.blocked_reason.lower()

    def test_check_entry_drawdown_at_limit_allowed(self):
        mgr = self._mgr(max_drawdown_pct=0.15)
        # Exactly at limit is NOT blocked (strict >)
        decision = mgr.check_entry(
            portfolio_equity=85_000.0,
            current_drawdown_pct=0.15,
            open_positions_count=0,
            deployed_capital=0.0,
        )
        assert decision.allowed is True

    # --- Rule 2: Max concurrent positions ---

    def test_check_entry_blocked_max_positions(self):
        mgr = self._mgr(max_concurrent_positions=5)
        decision = mgr.check_entry(
            portfolio_equity=100_000.0,
            current_drawdown_pct=0.0,
            open_positions_count=5,   # == limit
            deployed_capital=10_000.0,
        )
        assert decision.allowed is False
        assert "position" in decision.blocked_reason.lower()

    def test_check_entry_one_below_max_positions_allowed(self):
        mgr = self._mgr(max_concurrent_positions=5)
        decision = mgr.check_entry(
            portfolio_equity=100_000.0,
            current_drawdown_pct=0.0,
            open_positions_count=4,   # < limit
            deployed_capital=5_000.0,
        )
        assert decision.allowed is True

    # --- Rule 3: Portfolio exposure cap ---

    def test_check_entry_blocked_exposure(self):
        mgr = self._mgr(max_portfolio_exposure_pct=0.20, max_concurrent_positions=100)
        # deployed / equity = 20_001 / 100_000 = 20.001% > 20%
        decision = mgr.check_entry(
            portfolio_equity=100_000.0,
            current_drawdown_pct=0.0,
            open_positions_count=1,
            deployed_capital=20_001.0,
        )
        assert decision.allowed is False
        assert "exposure" in decision.blocked_reason.lower()

    def test_check_entry_exposure_just_below_limit_allowed(self):
        mgr = self._mgr(max_portfolio_exposure_pct=0.20, max_concurrent_positions=100)
        decision = mgr.check_entry(
            portfolio_equity=100_000.0,
            current_drawdown_pct=0.0,
            open_positions_count=1,
            deployed_capital=19_999.0,  # < 20%
        )
        assert decision.allowed is True

    def test_check_entry_zero_equity_skips_exposure_check(self):
        mgr = self._mgr(max_portfolio_exposure_pct=0.20)
        # When equity is 0, exposure check is skipped (avoids divide-by-zero)
        decision = mgr.check_entry(
            portfolio_equity=0.0,
            current_drawdown_pct=0.0,
            open_positions_count=0,
            deployed_capital=0.0,
        )
        assert decision.allowed is True

    # --- Rule priority: drawdown checked first ---

    def test_drawdown_blocks_before_position_check(self):
        mgr = self._mgr(max_drawdown_pct=0.10, max_concurrent_positions=5)
        decision = mgr.check_entry(
            portfolio_equity=100_000.0,
            current_drawdown_pct=0.20,   # >> limit
            open_positions_count=3,      # under positions limit
            deployed_capital=5_000.0,
        )
        assert decision.allowed is False
        # Drawdown reason should be mentioned
        assert "drawdown" in decision.blocked_reason.lower() or "kill" in decision.blocked_reason.lower()

    def test_effective_limits_returned_when_allowed(self):
        mgr = self._mgr(max_portfolio_exposure_pct=0.25, max_concurrent_positions=8)
        decision = mgr.check_entry(
            portfolio_equity=100_000.0,
            current_drawdown_pct=0.0,
            open_positions_count=0,
            deployed_capital=0.0,
        )
        assert decision.allowed is True
        assert decision.effective_max_exposure_pct == pytest.approx(0.25)
        assert decision.effective_max_positions == 8


# ===========================================================================
# 5. Regime-aware throttling
# ===========================================================================

class TestRegimeThrottling:
    """Tests for regime_risk_overrides logic in check_entry()."""

    def _mgr_with_overrides(self) -> PortfolioRiskManager:
        cfg = PortfolioRiskConfig(
            max_portfolio_exposure_pct=0.20,
            max_concurrent_positions=10,
            regime_risk_overrides={
                "risk_off": {
                    "max_portfolio_exposure_pct": 0.00,
                    "max_concurrent_positions": 0,
                },
                "bearish_volatile": {
                    "max_portfolio_exposure_pct": 0.05,
                    "max_concurrent_positions": 3,
                },
            },
        )
        return PortfolioRiskManager(config=cfg)

    def test_no_regime_label_uses_defaults(self):
        mgr = self._mgr_with_overrides()
        decision = mgr.check_entry(
            portfolio_equity=100_000.0,
            current_drawdown_pct=0.0,
            open_positions_count=0,
            deployed_capital=0.0,
            regime_label=None,
        )
        assert decision.allowed is True
        assert decision.regime_throttled is False
        assert decision.effective_max_exposure_pct == pytest.approx(0.20)
        assert decision.effective_max_positions == 10

    def test_unknown_regime_uses_defaults(self):
        mgr = self._mgr_with_overrides()
        decision = mgr.check_entry(
            portfolio_equity=100_000.0,
            current_drawdown_pct=0.0,
            open_positions_count=0,
            deployed_capital=0.0,
            regime_label="bullish_trending",  # not in overrides
        )
        assert decision.regime_throttled is False
        assert decision.effective_max_positions == 10

    def test_risk_off_blocks_all_entries(self):
        mgr = self._mgr_with_overrides()
        decision = mgr.check_entry(
            portfolio_equity=100_000.0,
            current_drawdown_pct=0.0,
            open_positions_count=0,
            deployed_capital=0.0,
            regime_label="risk_off",
        )
        assert decision.allowed is False
        assert decision.regime_throttled is True
        assert decision.effective_max_positions == 0

    def test_bearish_volatile_reduces_limits(self):
        mgr = self._mgr_with_overrides()
        # With 2 open positions, normally fine (limit 10) but bearish_volatile
        # caps to 3 -- still OK since 2 < 3
        decision = mgr.check_entry(
            portfolio_equity=100_000.0,
            current_drawdown_pct=0.0,
            open_positions_count=2,
            deployed_capital=2_000.0,
            regime_label="bearish_volatile",
        )
        assert decision.regime_throttled is True
        assert decision.effective_max_positions == 3
        assert decision.effective_max_exposure_pct == pytest.approx(0.05)

    def test_bearish_volatile_blocks_at_throttled_limit(self):
        mgr = self._mgr_with_overrides()
        # bearish_volatile: limit = 3 positions
        decision = mgr.check_entry(
            portfolio_equity=100_000.0,
            current_drawdown_pct=0.0,
            open_positions_count=3,   # == reduced limit
            deployed_capital=2_000.0,
            regime_label="bearish_volatile",
        )
        assert decision.allowed is False
        assert decision.regime_throttled is True

    def test_regime_throttled_flag_true_when_override_applied(self):
        mgr = self._mgr_with_overrides()
        decision = mgr.check_entry(
            portfolio_equity=100_000.0,
            current_drawdown_pct=0.0,
            open_positions_count=0,
            deployed_capital=0.0,
            regime_label="bearish_volatile",
        )
        assert decision.regime_throttled is True


# ===========================================================================
# 6. PortfolioRiskManager.compute_position_size()
# ===========================================================================

class TestComputePositionSize:
    """Tests for combined position sizing with risk limits."""

    def _mgr(self) -> PortfolioRiskManager:
        return PortfolioRiskManager(config=PortfolioRiskConfig(max_risk_per_trade_pct=0.01))

    def test_no_stop_loss_straight_allocation(self):
        mgr = self._mgr()
        # 95% of 10_000 / 100 = 95 units
        qty = mgr.compute_position_size(
            capital=10_000.0, price=100.0, portfolio_equity=100_000.0
        )
        assert qty == pytest.approx(95.0)

    def test_with_stop_loss_risk_limits(self):
        mgr = self._mgr()
        # Straight: 95% of 10_000 / 100 = 95 units
        # Risk-based: (100_000 * 1%) / 5% stop / 100 price = 200 units
        # -> min(95, 200) = 95 (straight allocation is tighter)
        qty = mgr.compute_position_size(
            capital=10_000.0, price=100.0,
            portfolio_equity=100_000.0, stop_loss_pct=0.05
        )
        assert qty == pytest.approx(95.0)

    def test_tight_stop_loss_reduces_quantity(self):
        mgr = self._mgr()
        # Straight: 95% of 50_000 / 100 = 475 units
        # Risk-based: (100_000 * 1%) / 50% stop = 2_000 capital / 100 price = 20 units
        # -> min(475, 20) = 20 (risk-based is tighter)
        qty = mgr.compute_position_size(
            capital=50_000.0, price=100.0,
            portfolio_equity=100_000.0, stop_loss_pct=0.50
        )
        assert qty == pytest.approx(20.0)

    def test_zero_stop_loss_ignored(self):
        mgr = self._mgr()
        qty_no_stop = mgr.compute_position_size(
            capital=10_000.0, price=100.0, portfolio_equity=100_000.0
        )
        qty_zero_stop = mgr.compute_position_size(
            capital=10_000.0, price=100.0,
            portfolio_equity=100_000.0, stop_loss_pct=0.0
        )
        assert qty_no_stop == pytest.approx(qty_zero_stop)

    def test_zero_price_returns_zero(self):
        mgr = self._mgr()
        qty = mgr.compute_position_size(
            capital=10_000.0, price=0.0, portfolio_equity=100_000.0
        )
        assert qty == 0.0


# ===========================================================================
# 7. PortfolioRiskManager.compute_drawdown()
# ===========================================================================

class TestComputeDrawdown:
    """Tests for the static drawdown computation helper."""

    def test_no_drawdown(self):
        eq = _make_equity_series([100.0, 110.0, 120.0, 130.0])
        current_dd, max_dd = PortfolioRiskManager.compute_drawdown(eq)
        assert current_dd == pytest.approx(0.0, abs=1e-6)
        assert max_dd == pytest.approx(0.0, abs=1e-6)

    def test_simple_drawdown(self):
        # Peak = 120, current = 90 -> dd = (120-90)/120 = 25%
        eq = _make_equity_series([100.0, 120.0, 90.0])
        current_dd, max_dd = PortfolioRiskManager.compute_drawdown(eq)
        assert current_dd == pytest.approx(0.25, rel=1e-4)
        assert max_dd == pytest.approx(0.25, rel=1e-4)

    def test_recovery_current_dd_near_zero(self):
        # Falls to 80 then recovers to 120 (above peak)
        eq = _make_equity_series([100.0, 80.0, 120.0])
        current_dd, max_dd = PortfolioRiskManager.compute_drawdown(eq)
        assert current_dd == pytest.approx(0.0, abs=1e-6)
        assert max_dd == pytest.approx(0.20, rel=1e-3)  # 20% drawdown occurred

    def test_empty_series(self):
        eq = pd.Series([], dtype=float)
        current_dd, max_dd = PortfolioRiskManager.compute_drawdown(eq)
        assert current_dd == 0.0
        assert max_dd == 0.0

    def test_single_element(self):
        eq = _make_equity_series([100.0])
        current_dd, max_dd = PortfolioRiskManager.compute_drawdown(eq)
        assert current_dd == 0.0
        assert max_dd == 0.0

    def test_monotone_decline(self):
        eq = _make_equity_series([100.0, 90.0, 80.0, 70.0])
        current_dd, max_dd = PortfolioRiskManager.compute_drawdown(eq)
        # Peak stays at 100; current at 70 -> dd = 30%
        assert current_dd == pytest.approx(0.30, rel=1e-4)
        assert max_dd == pytest.approx(0.30, rel=1e-4)

    def test_multiple_drawdown_segments(self):
        # DD1: 100 -> 80 (20%); DD2: 110 -> 85 (~22.7%)
        eq = _make_equity_series([100.0, 80.0, 110.0, 85.0])
        current_dd, max_dd = PortfolioRiskManager.compute_drawdown(eq)
        assert max_dd > 0.20


# ===========================================================================
# 8. validate_portfolio_risk()
# ===========================================================================

class TestValidatePortfolioRisk:
    """Tests for the post-hoc validation function."""

    def test_empty_df_returns_violation(self):
        violations = validate_portfolio_risk(pd.DataFrame())
        assert len(violations) == 1
        assert "empty" in violations[0].lower()

    def test_missing_equity_column_returns_violation(self):
        df = pd.DataFrame({"some_col": [100.0, 110.0]})
        violations = validate_portfolio_risk(df)
        assert len(violations) == 1
        assert "column" in violations[0].lower() or "cannot" in violations[0].lower()

    def test_clean_equity_curve_no_violations(self):
        # Growing equity, no drawdown concerns
        df = _make_equity_curve([100.0, 110.0, 120.0, 130.0])
        cfg = PortfolioRiskConfig(max_drawdown_pct=0.20)
        violations = validate_portfolio_risk(df, config=cfg)
        assert violations == []

    def test_max_drawdown_violation_detected(self):
        # 100 -> 80 = 20% dd (> 15% limit)
        df = _make_equity_curve([100.0, 80.0])
        cfg = PortfolioRiskConfig(max_drawdown_pct=0.15)
        violations = validate_portfolio_risk(df, config=cfg)
        assert len(violations) >= 1
        # At least one violation should mention drawdown
        texts = " ".join(v.lower() for v in violations)
        assert "drawdown" in texts

    def test_negative_equity_detected(self):
        df = _make_equity_curve([100.0, 50.0, -10.0])
        violations = validate_portfolio_risk(df)
        texts = " ".join(v.lower() for v in violations)
        assert "negative" in texts or "bankruptcy" in texts

    def test_fallback_equity_column_name(self):
        # validate_portfolio_risk also accepts "equity" column name
        df = pd.DataFrame({"equity": [100.0, 110.0, 120.0]})
        violations = validate_portfolio_risk(df)
        assert violations == []

    def test_default_config_used_when_none(self):
        df = _make_equity_curve([100.0, 105.0, 110.0])
        violations = validate_portfolio_risk(df, config=None)
        assert isinstance(violations, list)

    def test_total_return_worse_than_drawdown_limit(self):
        # total_return = -20% with default max_drawdown_pct=15%
        # This should trigger the return-on-risk sanity check
        df = _make_equity_curve([100.0, 80.0])
        cfg = PortfolioRiskConfig(max_drawdown_pct=0.15)
        violations = validate_portfolio_risk(df, config=cfg)
        # Should have at least the drawdown violation
        assert len(violations) >= 1

    def test_all_nan_equity_returns_violation(self):
        df = pd.DataFrame({"portfolio_equity": [float("nan"), float("nan")]})
        violations = validate_portfolio_risk(df)
        assert len(violations) >= 1

    def test_clean_curve_with_strict_limits(self):
        # Equity never falls - no drawdown violations with any threshold
        df = _make_equity_curve([100.0, 101.0, 102.0, 103.0, 104.0])
        cfg = PortfolioRiskConfig(max_drawdown_pct=0.01)  # very strict: 1%
        violations = validate_portfolio_risk(df, config=cfg)
        assert violations == []


# ===========================================================================
# 9. generate_risk_report()
# ===========================================================================

class TestGenerateRiskReport:
    """Tests for the markdown report generator."""

    def _clean_config(self) -> PortfolioRiskConfig:
        return PortfolioRiskConfig(
            max_risk_per_trade_pct=0.01,
            max_portfolio_exposure_pct=0.20,
            max_drawdown_pct=0.15,
            max_concurrent_positions=10,
        )

    def test_returns_string(self):
        cfg = self._clean_config()
        with tempfile.TemporaryDirectory() as tmp:
            content = generate_risk_report(
                cfg, [], output_path=Path(tmp) / "risk.md"
            )
        assert isinstance(content, str)
        assert len(content) > 0

    def test_pass_status_in_report(self):
        cfg = self._clean_config()
        with tempfile.TemporaryDirectory() as tmp:
            content = generate_risk_report(
                cfg, [], output_path=Path(tmp) / "risk.md"
            )
        assert "PASS" in content

    def test_violation_in_report(self):
        cfg = self._clean_config()
        violations = ["Max drawdown violation: 25.00% exceeded limit 15.00%."]
        with tempfile.TemporaryDirectory() as tmp:
            content = generate_risk_report(
                cfg, violations, output_path=Path(tmp) / "risk.md"
            )
        assert "VIOLATION" in content
        assert "Max drawdown" in content

    def test_file_written(self):
        cfg = self._clean_config()
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "risk_report.md"
            generate_risk_report(cfg, [], output_path=out_path)
            assert out_path.exists()
            assert out_path.stat().st_size > 0

    def test_file_content_matches_return_value(self):
        cfg = self._clean_config()
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "risk.md"
            content = generate_risk_report(cfg, [], output_path=out_path)
            assert out_path.read_text(encoding="utf-8") == content

    def test_config_values_in_report(self):
        cfg = self._clean_config()
        with tempfile.TemporaryDirectory() as tmp:
            content = generate_risk_report(
                cfg, [], output_path=Path(tmp) / "risk.md"
            )
        assert "1.00%" in content   # max_risk_per_trade
        assert "20.00%" in content  # max_portfolio_exposure
        assert "15.00%" in content  # max_drawdown
        assert "10" in content      # max_concurrent_positions

    def test_metadata_in_report(self):
        cfg = self._clean_config()
        meta = {"interval": "day", "symbols_tested": 5}
        with tempfile.TemporaryDirectory() as tmp:
            content = generate_risk_report(
                cfg, [], output_path=Path(tmp) / "risk.md",
                metadata=meta
            )
        assert "day" in content
        assert "5" in content

    def test_equity_curve_drawdown_in_report(self):
        cfg = self._clean_config()
        eq_curve = _make_equity_curve([100.0, 90.0, 110.0])
        with tempfile.TemporaryDirectory() as tmp:
            content = generate_risk_report(
                cfg, [], equity_curve=eq_curve,
                output_path=Path(tmp) / "risk.md"
            )
        # Drawdown summary section should appear
        assert "Drawdown" in content

    def test_default_output_path(self, tmp_path, monkeypatch):
        # When no output_path provided, it defaults to research/risk_engine_validation.md
        # We monkeypatch the cwd to tmp_path so it doesn't write to the real project
        monkeypatch.chdir(tmp_path)
        cfg = self._clean_config()
        content = generate_risk_report(cfg, [])
        expected = tmp_path / "research" / "risk_engine_validation.md"
        assert expected.exists()

    def test_regime_overrides_in_report(self):
        cfg = PortfolioRiskConfig(
            regime_risk_overrides={
                "risk_off": {"max_portfolio_exposure_pct": 0.00, "max_concurrent_positions": 0}
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            content = generate_risk_report(
                cfg, [], output_path=Path(tmp) / "risk.md"
            )
        assert "risk_off" in content

    def test_ascii_only_output(self):
        cfg = self._clean_config()
        with tempfile.TemporaryDirectory() as tmp:
            content = generate_risk_report(
                cfg, [], output_path=Path(tmp) / "risk.md"
            )
        # All characters should be encodable as cp1252 (Windows-safe)
        content.encode("cp1252")

    def test_multiple_violations_all_present(self):
        cfg = self._clean_config()
        violations = [
            "Max drawdown violation: 20.00% exceeded limit 15.00%.",
            "Portfolio equity went negative (bankruptcy) during the backtest.",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            content = generate_risk_report(
                cfg, violations, output_path=Path(tmp) / "risk.md"
            )
        assert "2 VIOLATION" in content
        assert "negative" in content.lower() or "bankruptcy" in content.lower()


# ===========================================================================
# 10. Public exports (__init__.py)
# ===========================================================================

class TestRiskPackageExports:
    """Verify that src/risk/__init__.py exports the expected symbols."""

    def test_portfolio_risk_config_importable(self):
        from src.risk import PortfolioRiskConfig  # noqa: F401

    def test_position_sizer_importable(self):
        from src.risk import PositionSizer  # noqa: F401

    def test_risk_decision_importable(self):
        from src.risk import RiskDecision  # noqa: F401

    def test_portfolio_risk_manager_importable(self):
        from src.risk import PortfolioRiskManager  # noqa: F401

    def test_validate_portfolio_risk_importable(self):
        from src.risk import validate_portfolio_risk  # noqa: F401

    def test_generate_risk_report_importable(self):
        from src.risk import generate_risk_report  # noqa: F401

    def test_all_exports_callable_or_instantiable(self):
        from src.risk import (
            PortfolioRiskConfig,
            PortfolioRiskManager,
            PositionSizer,
            RiskDecision,
            generate_risk_report,
            validate_portfolio_risk,
        )
        # Instantiations / callable checks
        _ = PortfolioRiskConfig()
        _ = PortfolioRiskManager()
        _ = PositionSizer()
        _ = RiskDecision(allowed=True)
        assert callable(validate_portfolio_risk)
        assert callable(generate_risk_report)
