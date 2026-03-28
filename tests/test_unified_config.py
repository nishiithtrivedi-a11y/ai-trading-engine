import os
import pytest
from pathlib import Path
from pydantic import BaseModel
from src.utils.unified_config import UnifiedConfig, load_unified_config

class DummyConfig(BaseModel):
    alpha: int = 10
    beta: str = "default_beta"
    gamma: bool = False


def test_unified_config_defaults():
    # Only code defaults
    cfg = load_unified_config(DummyConfig, env_prefix="TEST_")
    assert cfg.alpha == 10
    assert cfg.beta == "default_beta"
    assert cfg.gamma is False

def test_unified_config_env_overrides(monkeypatch):
    monkeypatch.setenv("TEST_ALPHA", "42")
    monkeypatch.setenv("TEST_GAMMA", "true")
    
    cfg = load_unified_config(DummyConfig, env_prefix="TEST_")
    assert cfg.alpha == 42
    assert cfg.gamma is True
    assert cfg.beta == "default_beta"

def test_unified_config_explicit_overrides(monkeypatch):
    monkeypatch.setenv("TEST_ALPHA", "42")
    
    # Explicit python overrides win over ENV
    cfg = load_unified_config(DummyConfig, overrides={"alpha": 99, "beta": "explicit"}, env_prefix="TEST_")
    assert cfg.alpha == 99
    assert cfg.beta == "explicit"
