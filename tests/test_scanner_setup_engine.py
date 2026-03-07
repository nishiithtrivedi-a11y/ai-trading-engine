from __future__ import annotations

import pandas as pd
import pytest

from src.core.data_handler import DataHandler
from src.scanners.config import ScannerConfig, SetupMode
from src.scanners.models import SignalSnapshot
from src.scanners.setup_engine import SetupEngine, SetupEngineError


def _build_data(num_bars: int = 50, flat: bool = False) -> DataHandler:
    if flat:
        close = [100.0 for _ in range(num_bars)]
        high = [100.0 for _ in range(num_bars)]
        low = [100.0 for _ in range(num_bars)]
        open_ = [100.0 for _ in range(num_bars)]
    else:
        open_ = [100 + i * 0.5 for i in range(num_bars)]
        high = [101 + i * 0.5 for i in range(num_bars)]
        low = [99 + i * 0.5 for i in range(num_bars)]
        close = [100.2 + i * 0.5 for i in range(num_bars)]

    df = pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": [1000 + i * 10 for i in range(num_bars)],
        },
        index=pd.date_range("2026-01-01", periods=num_bars, freq="D", name="timestamp"),
    )
    return DataHandler(df)


def _buy_signal(price: float = 150.0) -> SignalSnapshot:
    return SignalSnapshot(
        symbol="RELIANCE.NS",
        timeframe="1D",
        strategy_name="Dummy",
        signal="buy",
        timestamp=pd.Timestamp("2026-02-01"),
        close_price=price,
    )


def test_fixed_pct_stop_setup() -> None:
    dh = _build_data(50)
    cfg = ScannerConfig(
        setup_mode=SetupMode.FIXED_PCT,
        setup_fixed_stop_pct=0.02,
        setup_target_rr=2.0,
    )
    engine = SetupEngine()

    setup = engine.build_setup(_buy_signal(100.0), dh, cfg)

    assert setup.entry_price == pytest.approx(100.0)
    assert setup.stop_loss == pytest.approx(98.0)
    assert setup.target_price == pytest.approx(104.0)
    assert setup.risk_reward_ratio == pytest.approx(2.0)


def test_atr_stop_setup() -> None:
    dh = _build_data(60)
    cfg = ScannerConfig(
        setup_mode=SetupMode.ATR_R_MULTIPLE,
        setup_atr_period=14,
        setup_stop_atr_mult=1.5,
        setup_target_rr=2.0,
    )
    engine = SetupEngine()

    setup = engine.build_setup(_buy_signal(140.0), dh, cfg)

    assert setup.stop_loss < setup.entry_price
    assert setup.target_price > setup.entry_price
    assert setup.risk_reward_ratio == pytest.approx(2.0)


def test_target_generation_from_r_multiple() -> None:
    dh = _build_data(50)
    cfg = ScannerConfig(
        setup_mode=SetupMode.FIXED_PCT,
        setup_fixed_stop_pct=0.01,
        setup_target_rr=3.0,
    )
    engine = SetupEngine()

    setup = engine.build_setup(_buy_signal(200.0), dh, cfg)

    risk = 200.0 - 198.0
    assert setup.target_price == pytest.approx(200.0 + risk * 3.0)


def test_non_actionable_signal_raises() -> None:
    dh = _build_data(50)
    cfg = ScannerConfig(setup_mode=SetupMode.FIXED_PCT)
    engine = SetupEngine()
    hold_signal = SignalSnapshot(
        symbol="RELIANCE.NS",
        timeframe="1D",
        strategy_name="Dummy",
        signal="hold",
        timestamp=pd.Timestamp("2026-02-01"),
        close_price=120.0,
    )

    with pytest.raises(SetupEngineError, match="non-actionable"):
        engine.build_setup(hold_signal, dh, cfg)


def test_atr_invalid_when_flat_data_raises() -> None:
    dh = _build_data(50, flat=True)
    cfg = ScannerConfig(
        setup_mode=SetupMode.ATR_R_MULTIPLE,
        setup_atr_period=14,
        setup_stop_atr_mult=1.5,
    )
    engine = SetupEngine()

    with pytest.raises(SetupEngineError, match="ATR"):
        engine.build_setup(_buy_signal(100.0), dh, cfg)


def test_setup_rejected_when_stop_too_small() -> None:
    dh = _build_data(50)
    cfg = ScannerConfig(
        setup_mode=SetupMode.FIXED_PCT,
        setup_fixed_stop_pct=0.001,
        setup_min_stop_distance_pct=0.01,
    )
    engine = SetupEngine()

    with pytest.raises(SetupEngineError, match="below minimum"):
        engine.build_setup(_buy_signal(100.0), dh, cfg)


def test_setup_rejected_when_stop_too_large() -> None:
    dh = _build_data(60)
    cfg = ScannerConfig(
        setup_mode=SetupMode.ATR_R_MULTIPLE,
        setup_atr_period=14,
        setup_stop_atr_mult=8.0,
        setup_max_stop_distance_pct=0.05,
    )
    engine = SetupEngine()

    with pytest.raises(SetupEngineError, match="above maximum"):
        engine.build_setup(_buy_signal(140.0), dh, cfg)


def test_setup_rejected_when_rr_below_minimum() -> None:
    dh = _build_data(50)
    cfg = ScannerConfig(
        setup_mode=SetupMode.FIXED_PCT,
        setup_fixed_stop_pct=0.02,
        setup_target_rr=1.5,
        setup_min_rr=1.8,
    )
    engine = SetupEngine()

    with pytest.raises(SetupEngineError, match="below minimum"):
        engine.build_setup(_buy_signal(100.0), dh, cfg)
