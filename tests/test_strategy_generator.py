"""Tests for AI strategy generation and ranking (Step 12)."""

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from src.core.data_handler import DataHandler
from src.research.strategy_generator import (
    GeneratorResult,
    RankedStrategy,
    StrategyGenerator,
    StrategyRanker,
    StrategyTemplate,
    get_default_templates,
)
from src.strategies.breakout import BreakoutStrategy
from src.strategies.rsi_reversion import RSIReversionStrategy
from src.strategies.sma_crossover import SMACrossoverStrategy
from src.utils.config import BacktestConfig, PositionSizingMethod, RiskConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_config(tmp_path: Path) -> BacktestConfig:
    return BacktestConfig(
        initial_capital=100_000,
        fee_rate=0.001,
        slippage_rate=0.0005,
        position_sizing=PositionSizingMethod.PERCENT_OF_EQUITY,
        position_size_pct=0.95,
        intraday=False,
        risk=RiskConfig(
            stop_loss_pct=0.05,
            trailing_stop_pct=0.03,
        ),
        strategy_params={},
        output_dir=str(tmp_path / "backtest"),
        data_file="data/sample_data.csv",
    )


def _build_data(num_bars: int = 250) -> DataHandler:
    df = pd.DataFrame(
        {
            "open": [100 + i * 0.2 for i in range(num_bars)],
            "high": [101 + i * 0.2 for i in range(num_bars)],
            "low": [99 + i * 0.2 for i in range(num_bars)],
            "close": [100 + i * 0.25 for i in range(num_bars)],
            "volume": [1000 + i * 5 for i in range(num_bars)],
        },
        index=pd.date_range("2024-01-01", periods=num_bars, freq="D", name="timestamp"),
    )
    return DataHandler(df)


# ---------------------------------------------------------------------------
# Tests — StrategyTemplate
# ---------------------------------------------------------------------------

class TestStrategyTemplate:

    def test_name(self):
        t = StrategyTemplate(
            strategy_class=SMACrossoverStrategy,
            param_grid={"fast_period": [5, 10]},
        )
        assert t.name == "SMACrossoverStrategy"

    def test_num_combinations(self):
        t = StrategyTemplate(
            strategy_class=SMACrossoverStrategy,
            param_grid={
                "fast_period": [5, 10, 20],
                "slow_period": [30, 50],
            },
        )
        assert t.num_combinations() == 6

    def test_single_param_combination(self):
        t = StrategyTemplate(
            strategy_class=RSIReversionStrategy,
            param_grid={"rsi_period": [14]},
        )
        assert t.num_combinations() == 1

    def test_tags_and_description(self):
        t = StrategyTemplate(
            strategy_class=BreakoutStrategy,
            param_grid={"entry_period": [20]},
            description="Donchian breakout",
            tags=["breakout", "channel"],
        )
        assert t.description == "Donchian breakout"
        assert "breakout" in t.tags


# ---------------------------------------------------------------------------
# Tests — StrategyGenerator
# ---------------------------------------------------------------------------

class TestStrategyGenerator:

    def test_add_template(self):
        gen = StrategyGenerator()
        gen.add_template(StrategyTemplate(
            strategy_class=SMACrossoverStrategy,
            param_grid={"fast_period": [5, 10]},
        ))
        assert len(gen.templates) == 1

    def test_add_templates(self):
        gen = StrategyGenerator()
        gen.add_templates([
            StrategyTemplate(
                strategy_class=SMACrossoverStrategy,
                param_grid={"fast_period": [5]},
            ),
            StrategyTemplate(
                strategy_class=RSIReversionStrategy,
                param_grid={"rsi_period": [14]},
            ),
        ])
        assert len(gen.templates) == 2

    def test_get_candidates(self):
        gen = StrategyGenerator()
        gen.add_template(StrategyTemplate(
            strategy_class=SMACrossoverStrategy,
            param_grid={
                "fast_period": [5, 10],
                "slow_period": [30, 50],
            },
        ))
        candidates = gen.get_candidates()
        assert len(candidates) == 4
        # Each candidate has the right keys
        for c in candidates:
            assert "strategy_class" in c
            assert "params" in c
            assert c["strategy_class"] is SMACrossoverStrategy

    def test_total_candidates(self):
        gen = StrategyGenerator()
        gen.add_template(StrategyTemplate(
            strategy_class=SMACrossoverStrategy,
            param_grid={"fast_period": [5, 10], "slow_period": [30]},
        ))
        gen.add_template(StrategyTemplate(
            strategy_class=RSIReversionStrategy,
            param_grid={"rsi_period": [7, 14]},
        ))
        assert gen.total_candidates() == 4  # 2 + 2

    def test_get_candidates_multiple_templates(self):
        gen = StrategyGenerator()
        gen.add_template(StrategyTemplate(
            strategy_class=SMACrossoverStrategy,
            param_grid={"fast_period": [5]},
            tags=["trend"],
        ))
        gen.add_template(StrategyTemplate(
            strategy_class=RSIReversionStrategy,
            param_grid={"rsi_period": [14]},
            tags=["reversion"],
        ))
        candidates = gen.get_candidates()
        assert len(candidates) == 2
        names = {c["strategy_class"].__name__ for c in candidates}
        assert "SMACrossoverStrategy" in names
        assert "RSIReversionStrategy" in names

    def test_empty_generator(self):
        gen = StrategyGenerator()
        assert gen.total_candidates() == 0
        assert gen.get_candidates() == []


# ---------------------------------------------------------------------------
# Tests — RankedStrategy
# ---------------------------------------------------------------------------

class TestRankedStrategy:

    def test_to_dict(self):
        rs = RankedStrategy(
            rank=1,
            strategy_name="SMACrossoverStrategy",
            params={"fast_period": 10, "slow_period": 30},
            metrics={"sharpe_ratio": 1.5, "total_return_pct": 0.12},
            description="SMA crossover",
            tags=["trend"],
        )
        d = rs.to_dict()
        assert d["rank"] == 1
        assert d["param_fast_period"] == 10
        assert d["sharpe_ratio"] == 1.5
        assert d["tags"] == "trend"


# ---------------------------------------------------------------------------
# Tests — GeneratorResult
# ---------------------------------------------------------------------------

class TestGeneratorResult:

    def test_empty_result(self):
        r = GeneratorResult()
        assert r.to_dataframe().empty
        assert r.get_top(5) == []

    def test_to_dataframe(self):
        rs = RankedStrategy(
            rank=1,
            strategy_name="SMA",
            params={"fast": 5},
            metrics={"sharpe_ratio": 1.0},
        )
        r = GeneratorResult(ranked_strategies=[rs], total_candidates=1, total_successful=1)
        df = r.to_dataframe()
        assert len(df) == 1
        assert "rank" in df.columns

    def test_to_dict(self):
        r = GeneratorResult(
            ranked_strategies=[],
            total_candidates=10,
            total_successful=8,
            rank_metric="sharpe_ratio",
        )
        d = r.to_dict()
        assert d["total_candidates"] == 10
        assert d["total_successful"] == 8
        assert d["rank_metric"] == "sharpe_ratio"


# ---------------------------------------------------------------------------
# Tests — StrategyRanker
# ---------------------------------------------------------------------------

class TestStrategyRanker:

    def test_basic_ranking(self, tmp_path):
        config = _build_config(tmp_path)
        dh = _build_data(200)

        gen = StrategyGenerator()
        gen.add_template(StrategyTemplate(
            strategy_class=SMACrossoverStrategy,
            param_grid={"fast_period": [5, 10], "slow_period": [30]},
        ))

        ranker = StrategyRanker(
            base_config=config,
            rank_by="sharpe_ratio",
            output_dir=str(tmp_path / "ranking"),
        )
        result = ranker.run(dh, gen.get_candidates())

        assert isinstance(result, GeneratorResult)
        assert result.total_candidates == 2
        assert result.total_successful >= 1
        assert len(result.ranked_strategies) >= 1

        # Strategies should be ranked (rank 1 is best)
        if len(result.ranked_strategies) >= 2:
            first = result.ranked_strategies[0]
            second = result.ranked_strategies[1]
            assert first.rank == 1
            assert second.rank == 2

    def test_ranking_with_multiple_strategies(self, tmp_path):
        config = _build_config(tmp_path)
        dh = _build_data(200)

        gen = StrategyGenerator()
        gen.add_template(StrategyTemplate(
            strategy_class=SMACrossoverStrategy,
            param_grid={"fast_period": [5], "slow_period": [30]},
        ))
        gen.add_template(StrategyTemplate(
            strategy_class=BreakoutStrategy,
            param_grid={"entry_period": [20], "exit_period": [10]},
        ))

        ranker = StrategyRanker(
            base_config=config,
            rank_by="total_return_pct",
            output_dir=str(tmp_path / "ranking"),
        )
        result = ranker.run(dh, gen.get_candidates())

        assert result.total_candidates == 2
        names = {s.strategy_name for s in result.ranked_strategies}
        assert "SMACrossoverStrategy" in names or "BreakoutStrategy" in names

    def test_exports_created(self, tmp_path):
        config = _build_config(tmp_path)
        dh = _build_data(200)
        out_dir = tmp_path / "ranking_export"

        gen = StrategyGenerator()
        gen.add_template(StrategyTemplate(
            strategy_class=SMACrossoverStrategy,
            param_grid={"fast_period": [5], "slow_period": [30]},
        ))

        ranker = StrategyRanker(
            base_config=config,
            output_dir=str(out_dir),
        )
        ranker.run(dh, gen.get_candidates())

        assert (out_dir / "strategy_ranking.csv").exists()
        assert (out_dir / "strategy_ranking.json").exists()

        with open(out_dir / "strategy_ranking.json") as f:
            data = json.load(f)
        assert "total_candidates" in data
        assert isinstance(data["strategies"], list)

    def test_get_results_returns_last_run(self, tmp_path):
        config = _build_config(tmp_path)
        dh = _build_data(200)

        gen = StrategyGenerator()
        gen.add_template(StrategyTemplate(
            strategy_class=SMACrossoverStrategy,
            param_grid={"fast_period": [5], "slow_period": [30]},
        ))

        ranker = StrategyRanker(
            base_config=config,
            output_dir=str(tmp_path / "ranking"),
        )
        result = ranker.run(dh, gen.get_candidates())
        assert ranker.get_results() is result

    def test_top_n_limits_output(self, tmp_path):
        config = _build_config(tmp_path)
        dh = _build_data(200)

        gen = StrategyGenerator()
        gen.add_template(StrategyTemplate(
            strategy_class=SMACrossoverStrategy,
            param_grid={"fast_period": [5, 10, 15], "slow_period": [30, 50]},
        ))

        ranker = StrategyRanker(
            base_config=config,
            top_n=3,
            output_dir=str(tmp_path / "ranking"),
        )
        result = ranker.run(dh, gen.get_candidates())
        assert len(result.ranked_strategies) <= 3

    def test_result_json_serializable(self, tmp_path):
        config = _build_config(tmp_path)
        dh = _build_data(200)

        gen = StrategyGenerator()
        gen.add_template(StrategyTemplate(
            strategy_class=SMACrossoverStrategy,
            param_grid={"fast_period": [5], "slow_period": [30]},
        ))

        ranker = StrategyRanker(
            base_config=config,
            output_dir=str(tmp_path / "ranking"),
        )
        result = ranker.run(dh, gen.get_candidates())
        json_str = json.dumps(result.to_dict(), default=str)
        assert isinstance(json_str, str)


# ---------------------------------------------------------------------------
# Tests — get_default_templates
# ---------------------------------------------------------------------------

class TestDefaultTemplates:

    def test_returns_templates(self):
        templates = get_default_templates()
        assert isinstance(templates, list)
        assert len(templates) >= 3

    def test_all_are_strategy_templates(self):
        templates = get_default_templates()
        for t in templates:
            assert isinstance(t, StrategyTemplate)
            assert t.param_grid  # Not empty
            assert t.description  # Has description

    def test_total_combinations(self):
        templates = get_default_templates()
        total = sum(t.num_combinations() for t in templates)
        # 9 (SMA) + 12 (RSI) + 9 (Breakout) = 30
        assert total == 30

    def test_templates_have_tags(self):
        templates = get_default_templates()
        for t in templates:
            assert len(t.tags) > 0
