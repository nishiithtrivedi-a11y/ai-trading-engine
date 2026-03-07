from __future__ import annotations

from pathlib import Path

import pytest

from src.realtime.config import RealTimeEngineConfig, RealtimeConfig, load_realtime_config
from src.realtime.models import RealTimeMode


def test_realtime_defaults_are_safe_off() -> None:
    cfg = RealtimeConfig()
    assert cfg.enabled is False
    assert cfg.mode == RealTimeMode.OFF
    assert cfg.poll_interval_seconds == 60
    assert cfg.max_cycles_per_run == 5
    assert cfg.timeframes == ["1D"]


def test_realtime_enabled_requires_non_off_mode() -> None:
    with pytest.raises(ValueError, match="mode cannot be 'off'"):
        RealtimeConfig(enabled=True, mode=RealTimeMode.OFF)


def test_realtime_enabled_simulated_mode_ok() -> None:
    cfg = RealtimeConfig(enabled=True, mode=RealTimeMode.SIMULATED, timeframes=["1d", "5M"])
    assert cfg.mode == RealTimeMode.SIMULATED
    assert cfg.timeframes == ["1D", "5m"]


def test_realtime_disabled_forces_off_mode() -> None:
    cfg = RealtimeConfig(enabled=False, mode=RealTimeMode.POLLING)
    assert cfg.mode == RealTimeMode.OFF


def test_polling_mode_requires_polling_switch() -> None:
    with pytest.raises(ValueError, match="requires enable_polling=true"):
        RealtimeConfig(
            enabled=True,
            mode=RealTimeMode.POLLING,
            enable_polling=False,
        )


def test_load_realtime_config_from_yaml(tmp_path: Path) -> None:
    yaml_text = """
realtime:
  enabled: true
  mode: simulated
  poll_interval_seconds: 45
  symbols: [RELIANCE.NS, TCS.NS]
  timeframes: [1D, 15m]
"""
    cfg_path = tmp_path / "realtime.yaml"
    cfg_path.write_text(yaml_text, encoding="utf-8")

    cfg = load_realtime_config(str(cfg_path), base_config=RealTimeEngineConfig())
    assert cfg.realtime.enabled is True
    assert cfg.realtime.mode == RealTimeMode.SIMULATED
    assert cfg.realtime.poll_interval_seconds == 45
    assert cfg.realtime.symbols == ["RELIANCE.NS", "TCS.NS"]
    assert cfg.realtime.timeframes == ["1D", "15m"]
