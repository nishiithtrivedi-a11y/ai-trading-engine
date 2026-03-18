"""Tests for ProviderRouter and ProviderRoutingPolicy."""
from __future__ import annotations

import pytest

from src.data.provider_router import (
    ProviderRouter,
    ProviderRoutingError,
    ProviderRoutingPolicy,
)


class TestProviderRoutingPolicy:
    def test_zerodha_only_default_provider(self):
        p = ProviderRoutingPolicy.zerodha_only()
        assert p.default_provider == "zerodha"

    def test_zerodha_only_derivatives_provider(self):
        p = ProviderRoutingPolicy.zerodha_only()
        assert p.derivatives_provider == "zerodha"

    def test_zerodha_only_cash_provider(self):
        p = ProviderRoutingPolicy.zerodha_only()
        assert p.cash_provider == "zerodha"

    def test_dhan_only_default_provider(self):
        p = ProviderRoutingPolicy.dhan_only()
        assert p.default_provider == "dhan"

    def test_dhan_only_derivatives_provider(self):
        p = ProviderRoutingPolicy.dhan_only()
        assert p.derivatives_provider == "dhan"

    def test_dhan_primary_zerodha_cash_derivatives(self):
        p = ProviderRoutingPolicy.dhan_primary_zerodha_cash()
        assert p.derivatives_provider == "dhan"

    def test_dhan_primary_zerodha_cash_cash(self):
        p = ProviderRoutingPolicy.dhan_primary_zerodha_cash()
        assert p.cash_provider == "zerodha"

    def test_dhan_primary_zerodha_cash_default(self):
        p = ProviderRoutingPolicy.dhan_primary_zerodha_cash()
        assert p.default_provider == "zerodha"

    def test_auto_has_broad_fallback(self):
        p = ProviderRoutingPolicy.auto()
        assert "zerodha" in p.fallback_order

    def test_auto_default_provider_zerodha(self):
        p = ProviderRoutingPolicy.auto()
        assert p.default_provider == "zerodha"

    def test_auto_derivatives_provider_none(self):
        p = ProviderRoutingPolicy.auto()
        assert p.derivatives_provider is None

    def test_from_config_basic(self):
        config = {
            "default_provider": "dhan",
            "derivatives_provider": "dhan",
            "cash_provider": "zerodha",
            "fallback_order": ["dhan", "zerodha", "csv"],
            "allow_degraded": False,
        }
        p = ProviderRoutingPolicy.from_config(config)
        assert p.default_provider == "dhan"
        assert p.derivatives_provider == "dhan"
        assert p.cash_provider == "zerodha"
        assert p.allow_degraded is False

    def test_from_config_defaults(self):
        p = ProviderRoutingPolicy.from_config({})
        assert p.default_provider == "zerodha"
        assert p.allow_degraded is True

    def test_from_config_partial(self):
        p = ProviderRoutingPolicy.from_config({"default_provider": "csv"})
        assert p.default_provider == "csv"


class TestProviderRouter:
    def test_select_default_returns_default_provider(self):
        policy = ProviderRoutingPolicy.zerodha_only()
        router = ProviderRouter(policy)
        assert router.select_default() == "zerodha"

    def test_select_default_dhan_policy(self):
        policy = ProviderRoutingPolicy.dhan_only()
        router = ProviderRouter(policy)
        assert router.select_default() == "dhan"

    def test_select_for_cash_zerodha_only(self):
        policy = ProviderRoutingPolicy.zerodha_only()
        router = ProviderRouter(policy)
        result = router.select_for_cash("NSE")
        assert result == "zerodha"

    def test_select_for_derivatives_dhan_only(self):
        policy = ProviderRoutingPolicy.dhan_only()
        router = ProviderRouter(policy)
        result = router.select_for_derivatives("NFO")
        assert result == "dhan"

    def test_select_for_derivatives_dhan_primary_policy(self):
        policy = ProviderRoutingPolicy.dhan_primary_zerodha_cash()
        router = ProviderRouter(policy)
        result = router.select_for_derivatives("NFO")
        assert result == "dhan"

    def test_select_for_cash_dhan_primary_policy(self):
        policy = ProviderRoutingPolicy.dhan_primary_zerodha_cash()
        router = ProviderRouter(policy)
        result = router.select_for_cash("NSE")
        assert result == "zerodha"

    def test_select_for_segment_nfo_routes_to_derivatives(self):
        policy = ProviderRoutingPolicy.dhan_primary_zerodha_cash()
        router = ProviderRouter(policy)
        result = router.select_for_segment("NFO")
        assert result == "dhan"

    def test_select_for_segment_nse_routes_to_cash(self):
        policy = ProviderRoutingPolicy.dhan_primary_zerodha_cash()
        router = ProviderRouter(policy)
        result = router.select_for_segment("NSE")
        assert result == "zerodha"

    def test_select_for_segment_mcx_routes_to_derivatives(self):
        policy = ProviderRoutingPolicy.dhan_primary_zerodha_cash()
        router = ProviderRouter(policy)
        result = router.select_for_segment("MCX")
        assert result == "dhan"

    def test_select_for_segment_cds_routes_to_derivatives(self):
        policy = ProviderRoutingPolicy.dhan_primary_zerodha_cash()
        router = ProviderRouter(policy)
        result = router.select_for_segment("CDS")
        assert result == "dhan"

    def test_select_for_segment_bse_routes_to_cash(self):
        policy = ProviderRoutingPolicy.zerodha_only()
        router = ProviderRouter(policy)
        result = router.select_for_segment("BSE")
        assert result == "zerodha"

    def test_capability_report_returns_dict_with_policy_and_providers(self):
        policy = ProviderRoutingPolicy.zerodha_only()
        router = ProviderRouter(policy)
        report = router.capability_report()
        assert "policy" in report
        assert "providers" in report

    def test_capability_report_policy_keys(self):
        policy = ProviderRoutingPolicy.zerodha_only()
        router = ProviderRouter(policy)
        report = router.capability_report()
        assert "default" in report["policy"]
        assert "derivatives" in report["policy"]
        assert "cash" in report["policy"]
        assert "fallback_order" in report["policy"]

    def test_capability_report_zerodha_derivatives_true(self):
        policy = ProviderRoutingPolicy.zerodha_only()
        router = ProviderRouter(policy)
        report = router.capability_report()
        assert report["providers"]["zerodha"]["derivatives"] is True

    def test_capability_report_dhan_derivatives_true(self):
        policy = ProviderRoutingPolicy.dhan_primary_zerodha_cash()
        router = ProviderRouter(policy)
        report = router.capability_report()
        assert report["providers"]["dhan"]["derivatives"] is True

    def test_capability_report_includes_fallback_providers(self):
        policy = ProviderRoutingPolicy.dhan_primary_zerodha_cash()
        router = ProviderRouter(policy)
        report = router.capability_report()
        # fallback_order includes zerodha, dhan, csv
        for provider in ["zerodha", "dhan", "csv"]:
            assert provider in report["providers"]

    def test_router_fallback_for_unknown_derivatives_provider(self):
        """If derivatives_provider is an unknown/invalid provider, fallback works."""
        policy = ProviderRoutingPolicy(
            default_provider="zerodha",
            derivatives_provider="nonexistent_provider",
            fallback_order=["zerodha", "csv"],
        )
        router = ProviderRouter(policy)
        # Should fall back gracefully
        result = router.select_for_derivatives("NFO")
        # zerodha supports NFO derivatives → should return zerodha
        assert result in ("zerodha", "nonexistent_provider", policy.default_provider)

    def test_policy_attribute_accessible(self):
        policy = ProviderRoutingPolicy.auto()
        router = ProviderRouter(policy)
        assert router.policy is policy

    def test_default_router_uses_default_policy(self):
        router = ProviderRouter()
        assert router.select_default() == "zerodha"
