"""Tests for FuturesContractResolver, ContinuousSeriesBuilder."""
from __future__ import annotations

import pytest
import pandas as pd
from dataclasses import dataclass
from datetime import date
from typing import Optional

from src.analysis.derivatives.futures.intelligence import (
    ContinuousSeriesBuilder,
    ContinuousSeriesMetadata,
    FuturesContractFamily,
    FuturesContractInfo,
    FuturesContractResolver,
)


# ---------------------------------------------------------------------------
# Minimal mock instrument for registry tests
# ---------------------------------------------------------------------------

@dataclass
class _MockInstrument:
    symbol: str
    exchange: str
    expiry: Optional[date]
    canonical: str
    lot_size: Optional[int] = None
    tick_size: Optional[float] = None

    class _Type:
        value = "future"

    instrument_type: _Type = None

    def __post_init__(self):
        self.instrument_type = self._Type()


class _MockRegistry:
    def __init__(self, instruments):
        self._instruments = instruments

    def list_by_underlying(self, underlying):
        return [i for i in self._instruments if i.symbol == underlying]


# ---------------------------------------------------------------------------
# FuturesContractResolver tests
# ---------------------------------------------------------------------------

class TestFuturesContractResolver:
    def _resolver(self, threshold=5) -> FuturesContractResolver:
        return FuturesContractResolver(roll_day_threshold=threshold)

    def test_days_to_expiry_basic(self):
        resolver = self._resolver()
        expiry = date(2026, 4, 30)
        as_of = date(2026, 3, 18)
        dte = resolver.days_to_expiry(expiry, as_of=as_of)
        assert dte == 43

    def test_days_to_expiry_same_day(self):
        resolver = self._resolver()
        today = date(2026, 3, 18)
        assert resolver.days_to_expiry(today, as_of=today) == 0

    def test_days_to_expiry_past_expiry_returns_zero(self):
        resolver = self._resolver()
        expiry = date(2026, 3, 10)
        assert resolver.days_to_expiry(expiry, as_of=date(2026, 3, 18)) == 0

    def test_is_roll_imminent_true_within_threshold(self):
        resolver = self._resolver(threshold=5)
        expiry = date(2026, 3, 20)
        assert resolver.is_roll_imminent(expiry, as_of=date(2026, 3, 18)) is True

    def test_is_roll_imminent_false_outside_threshold(self):
        resolver = self._resolver(threshold=5)
        expiry = date(2026, 4, 30)
        assert resolver.is_roll_imminent(expiry, as_of=date(2026, 3, 18)) is False

    def test_is_roll_imminent_at_threshold_boundary(self):
        resolver = self._resolver(threshold=5)
        # exactly 5 days away → imminent
        expiry = date(2026, 3, 23)
        assert resolver.is_roll_imminent(expiry, as_of=date(2026, 3, 18)) is True

    def test_compute_basis_contango(self):
        resolver = self._resolver()
        result = resolver.compute_basis(22000, 22100)
        assert result["basis"] == pytest.approx(100)
        assert result["contango"] is True
        assert result["backwardation"] is False
        assert result["basis_pct"] == pytest.approx(100 / 22000 * 100)

    def test_compute_basis_backwardation(self):
        resolver = self._resolver()
        result = resolver.compute_basis(22100, 22000)
        assert result["basis"] == pytest.approx(-100)
        assert result["backwardation"] is True
        assert result["contango"] is False

    def test_compute_basis_flat(self):
        resolver = self._resolver()
        result = resolver.compute_basis(22000, 22000)
        assert result["basis"] == pytest.approx(0)
        assert result["contango"] is False
        assert result["backwardation"] is False

    def test_get_contract_family_returns_family(self):
        instruments = [
            _MockInstrument("NIFTY", "NFO", date(2026, 3, 27), "NFO:NIFTY-2026-03-27-FUT"),
            _MockInstrument("NIFTY", "NFO", date(2026, 4, 30), "NFO:NIFTY-2026-04-30-FUT"),
            _MockInstrument("NIFTY", "NFO", date(2026, 5, 28), "NFO:NIFTY-2026-05-28-FUT"),
        ]
        registry = _MockRegistry(instruments)
        resolver = self._resolver()
        family = resolver.get_contract_family(registry, "NIFTY", "NFO", as_of=date(2026, 3, 18))

        assert isinstance(family, FuturesContractFamily)
        assert family.underlying == "NIFTY"
        assert len(family.contracts) == 3

    def test_get_contract_family_front_is_first(self):
        instruments = [
            _MockInstrument("NIFTY", "NFO", date(2026, 3, 27), "NFO:NIFTY-2026-03-27-FUT"),
            _MockInstrument("NIFTY", "NFO", date(2026, 4, 30), "NFO:NIFTY-2026-04-30-FUT"),
        ]
        registry = _MockRegistry(instruments)
        resolver = self._resolver()
        family = resolver.get_contract_family(registry, "NIFTY", "NFO", as_of=date(2026, 3, 18))
        assert family.front is not None
        assert family.front.expiry == date(2026, 3, 27)

    def test_get_contract_family_next_is_second(self):
        instruments = [
            _MockInstrument("NIFTY", "NFO", date(2026, 3, 27), "NFO:NIFTY-2026-03-27-FUT"),
            _MockInstrument("NIFTY", "NFO", date(2026, 4, 30), "NFO:NIFTY-2026-04-30-FUT"),
        ]
        registry = _MockRegistry(instruments)
        resolver = self._resolver()
        family = resolver.get_contract_family(registry, "NIFTY", "NFO", as_of=date(2026, 3, 18))
        assert family.next_contract is not None
        assert family.next_contract.expiry == date(2026, 4, 30)

    def test_family_is_roll_imminent_when_front_dte_within_threshold(self):
        instruments = [
            _MockInstrument("NIFTY", "NFO", date(2026, 3, 20), "NFO:NIFTY-2026-03-20-FUT"),
            _MockInstrument("NIFTY", "NFO", date(2026, 4, 30), "NFO:NIFTY-2026-04-30-FUT"),
        ]
        registry = _MockRegistry(instruments)
        resolver = self._resolver(threshold=5)
        family = resolver.get_contract_family(registry, "NIFTY", "NFO", as_of=date(2026, 3, 18))
        # front expires in 2 days → imminent
        assert family.is_roll_imminent is True

    def test_family_is_not_roll_imminent_when_dte_high(self):
        instruments = [
            _MockInstrument("NIFTY", "NFO", date(2026, 4, 30), "NFO:NIFTY-2026-04-30-FUT"),
        ]
        registry = _MockRegistry(instruments)
        resolver = self._resolver(threshold=5)
        family = resolver.get_contract_family(registry, "NIFTY", "NFO", as_of=date(2026, 3, 18))
        assert family.is_roll_imminent is False

    def test_get_roll_signal_no_front(self):
        resolver = self._resolver()
        family = FuturesContractFamily(underlying="NIFTY", exchange="NFO", as_of=date.today())
        signal = resolver.get_roll_signal(family)
        assert signal["action"] == "no_front_contract"
        assert signal["imminent"] is False

    def test_get_roll_signal_hold_front(self):
        resolver = self._resolver(threshold=5)
        contract_info = FuturesContractInfo(
            canonical="NFO:NIFTY-2026-04-30-FUT",
            underlying="NIFTY",
            exchange="NFO",
            expiry=date(2026, 4, 30),
            days_to_expiry=43,
            contract_position="front",
        )
        family = FuturesContractFamily(underlying="NIFTY", exchange="NFO", as_of=date(2026, 3, 18))
        family.contracts = [contract_info]
        signal = resolver.get_roll_signal(family)
        assert signal["action"] == "hold_front"
        assert signal["imminent"] is False

    def test_get_roll_signal_roll_to_next(self):
        resolver = self._resolver(threshold=5)
        front = FuturesContractInfo(
            canonical="NFO:NIFTY-2026-03-27-FUT",
            underlying="NIFTY",
            exchange="NFO",
            expiry=date(2026, 3, 20),
            days_to_expiry=2,
            contract_position="front",
        )
        next_c = FuturesContractInfo(
            canonical="NFO:NIFTY-2026-04-30-FUT",
            underlying="NIFTY",
            exchange="NFO",
            expiry=date(2026, 4, 30),
            days_to_expiry=43,
            contract_position="next",
        )
        family = FuturesContractFamily(underlying="NIFTY", exchange="NFO", as_of=date(2026, 3, 18))
        family.contracts = [front, next_c]
        signal = resolver.get_roll_signal(family)
        assert signal["action"] == "roll_to_next"
        assert signal["imminent"] is True
        assert signal["next_expiry"] == str(next_c.expiry)


# ---------------------------------------------------------------------------
# ContinuousSeriesBuilder tests
# ---------------------------------------------------------------------------

class TestContinuousSeriesBuilder:
    def _builder(self, method="dte_roll", roll_days=5) -> ContinuousSeriesBuilder:
        return ContinuousSeriesBuilder(method=method, roll_days=roll_days)

    def _instruments(self):
        return [
            _MockInstrument("NIFTY", "NFO", date(2026, 3, 27), "NFO:NIFTY-2026-03-27-FUT"),
            _MockInstrument("NIFTY", "NFO", date(2026, 4, 30), "NFO:NIFTY-2026-04-30-FUT"),
            _MockInstrument("NIFTY", "NFO", date(2026, 5, 28), "NFO:NIFTY-2026-05-28-FUT"),
        ]

    def test_build_roll_schedule_returns_metadata(self):
        builder = self._builder()
        meta = builder.build_roll_schedule(self._instruments(), as_of=date(2026, 3, 1))
        assert isinstance(meta, ContinuousSeriesMetadata)

    def test_build_roll_schedule_has_roll_dates(self):
        builder = self._builder()
        meta = builder.build_roll_schedule(self._instruments(), as_of=date(2026, 3, 1))
        assert len(meta.roll_dates) > 0

    def test_build_roll_schedule_has_contract_spans(self):
        builder = self._builder()
        meta = builder.build_roll_schedule(self._instruments(), as_of=date(2026, 3, 1))
        assert len(meta.contract_spans) > 0
        for span in meta.contract_spans:
            assert "contract" in span
            assert "from" in span
            assert "to" in span
            assert "expiry" in span

    def test_build_roll_schedule_dte_roll_date_before_expiry(self):
        builder = self._builder(method="dte_roll", roll_days=5)
        instruments = [
            _MockInstrument("NIFTY", "NFO", date(2026, 3, 27), "NFO:NIFTY-2026-03-27-FUT"),
        ]
        meta = builder.build_roll_schedule(instruments, as_of=date(2026, 3, 1))
        # Roll date should be 5 days before March 27 = March 22
        assert meta.roll_dates[0] == date(2026, 3, 22)

    def test_build_roll_schedule_calendar_roll(self):
        builder = self._builder(method="calendar_roll")
        instruments = [
            _MockInstrument("NIFTY", "NFO", date(2026, 3, 27), "NFO:NIFTY-2026-03-27-FUT"),
        ]
        meta = builder.build_roll_schedule(instruments, as_of=date(2026, 3, 1))
        # Calendar roll = expiry date itself
        assert meta.roll_dates[0] == date(2026, 3, 27)

    def test_stitch_from_dataframes_returns_dataframe(self):
        builder = self._builder()
        instruments = self._instruments()
        meta = builder.build_roll_schedule(instruments, as_of=date(2026, 3, 1))

        # Create dummy DataFrames
        idx1 = pd.date_range("2026-03-01", periods=5, freq="D")
        idx2 = pd.date_range("2026-03-22", periods=10, freq="D")
        contract_data = {
            instruments[0].canonical: pd.DataFrame({"open": 22000, "close": 22050}, index=idx1),
            instruments[1].canonical: pd.DataFrame({"open": 22100, "close": 22150}, index=idx2),
        }
        result = builder.stitch_from_dataframes(contract_data, meta)
        assert isinstance(result, pd.DataFrame)

    def test_stitch_from_dataframes_has_contract_column(self):
        builder = self._builder()
        instruments = self._instruments()
        meta = builder.build_roll_schedule(instruments, as_of=date(2026, 3, 1))

        idx = pd.date_range("2026-03-01", periods=5, freq="D")
        contract_data = {
            instruments[0].canonical: pd.DataFrame({"open": 22000, "close": 22050}, index=idx),
        }
        result = builder.stitch_from_dataframes(contract_data, meta)
        if not result.empty:
            assert "contract" in result.columns

    def test_stitch_from_dataframes_empty_data_returns_empty_df(self):
        builder = self._builder()
        instruments = self._instruments()
        meta = builder.build_roll_schedule(instruments, as_of=date(2026, 3, 1))
        result = builder.stitch_from_dataframes({}, meta)
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    def test_build_roll_schedule_notes_scaffold(self):
        builder = self._builder()
        meta = builder.build_roll_schedule(self._instruments(), as_of=date(2026, 3, 1))
        assert any("scaffold_only" in n for n in meta.notes)
