"""
Phase 7 strategy candidate generator.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

from src.research.strategy_generator import StrategyTemplate, get_default_templates
from src.research_lab.config import ResearchLabGeneratorConfig
from src.research_lab.models import StrategyCandidate
from src.strategies.breakout import BreakoutStrategy
from src.strategies.rsi_reversion import RSIReversionStrategy
from src.strategies.sma_crossover import SMACrossoverStrategy


class StrategyGeneratorLabError(Exception):
    """Raised when strategy candidate generation fails."""


_KNOWN_STRATEGIES = {
    "SMACrossoverStrategy": SMACrossoverStrategy,
    "RSIReversionStrategy": RSIReversionStrategy,
    "BreakoutStrategy": BreakoutStrategy,
}


@dataclass
class StrategyGeneratorLab:
    def generate(self, config: ResearchLabGeneratorConfig) -> list[StrategyCandidate]:
        templates: list[StrategyTemplate] = []

        if config.use_default_templates:
            templates.extend(get_default_templates())

        for strategy_name, param_grid in config.strategy_param_grids.items():
            strategy_class = _KNOWN_STRATEGIES.get(strategy_name)
            if strategy_class is None:
                raise StrategyGeneratorLabError(
                    f"Unknown strategy '{strategy_name}'. Known: {sorted(_KNOWN_STRATEGIES)}"
                )
            templates.append(
                StrategyTemplate(
                    strategy_class=strategy_class,
                    param_grid=param_grid,
                    description=f"custom_grid:{strategy_name}",
                    tags=["custom"],
                )
            )

        candidates: list[StrategyCandidate] = []
        for template in templates:
            candidates.extend(self._expand_template(template))

        # Deterministic ordering + dedupe by key.
        deduped: dict[str, StrategyCandidate] = {}
        for candidate in sorted(candidates, key=lambda c: (c.strategy_name, sorted(c.params.items()))):
            deduped[candidate.key()] = candidate

        ordered = list(deduped.values())
        return ordered[: config.max_candidates]

    @staticmethod
    def _expand_template(template: StrategyTemplate) -> list[StrategyCandidate]:
        if not template.param_grid:
            return [
                StrategyCandidate(
                    strategy_class=template.strategy_class,
                    params={},
                    template_name=template.name,
                    tags=list(template.tags),
                    metadata={"description": template.description},
                )
            ]

        keys = list(template.param_grid.keys())
        values = [template.param_grid[k] for k in keys]

        out: list[StrategyCandidate] = []
        for combo in itertools.product(*values):
            params = dict(zip(keys, combo))
            out.append(
                StrategyCandidate(
                    strategy_class=template.strategy_class,
                    params=params,
                    template_name=template.name,
                    tags=list(template.tags),
                    metadata={"description": template.description},
                )
            )
        return out
