from __future__ import annotations

import pytest

from src.research_lab.config import ResearchLabGeneratorConfig
from src.research_lab.strategy_generator import StrategyGeneratorLab, StrategyGeneratorLabError


def test_generate_default_candidates() -> None:
    cfg = ResearchLabGeneratorConfig(use_default_templates=True, max_candidates=100)
    candidates = StrategyGeneratorLab().generate(cfg)
    assert len(candidates) > 0
    assert all(c.strategy_name for c in candidates)


def test_generate_custom_grid_candidates() -> None:
    cfg = ResearchLabGeneratorConfig(
        use_default_templates=False,
        strategy_param_grids={
            "SMACrossoverStrategy": {"fast_period": [5, 10], "slow_period": [30]},
        },
        max_candidates=10,
    )
    candidates = StrategyGeneratorLab().generate(cfg)
    assert len(candidates) == 2
    assert all(c.strategy_name == "SMACrossoverStrategy" for c in candidates)


def test_unknown_strategy_raises() -> None:
    cfg = ResearchLabGeneratorConfig(
        use_default_templates=False,
        strategy_param_grids={"UnknownStrategy": {"x": [1]}},
    )
    with pytest.raises(StrategyGeneratorLabError):
        StrategyGeneratorLab().generate(cfg)
