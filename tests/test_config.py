"""Tests for the configuration module."""

import pytest

from src.utils.config import BacktestConfig, DataSource, RiskConfig, load_config


class TestBacktestConfig:

    def test_default_config(self):
        config = BacktestConfig()
        assert config.initial_capital == 100_000
        assert config.fee_rate == 0.001
        assert config.slippage_rate == 0.0005

    def test_custom_config(self):
        config = BacktestConfig(
            initial_capital=50_000,
            fee_rate=0.002,
        )
        assert config.initial_capital == 50_000
        assert config.fee_rate == 0.002

    def test_invalid_capital(self):
        with pytest.raises(Exception):
            BacktestConfig(initial_capital=-1000)

    def test_invalid_data_file(self):
        with pytest.raises(Exception):
            BacktestConfig(data_file="data.txt")

    def test_load_config_defaults(self):
        config = load_config()
        assert config.initial_capital == 100_000

    def test_load_config_overrides(self):
        config = load_config({"initial_capital": 200_000, "fee_rate": 0.005})
        assert config.initial_capital == 200_000
        assert config.fee_rate == 0.005


class TestDataSource:

    def test_data_source_enum_values(self):
        assert DataSource.CSV == "csv"
        assert DataSource.INDIAN_CSV == "indian_csv"
        assert DataSource.ZERODHA == "zerodha"
        assert DataSource.UPSTOX == "upstox"

    def test_default_data_source_is_csv(self):
        config = BacktestConfig()
        assert config.data_source == DataSource.CSV

    def test_indian_csv_data_source(self):
        config = BacktestConfig(
            data_source=DataSource.INDIAN_CSV,
            data_file="data/nifty.csv",
        )
        assert config.data_source == DataSource.INDIAN_CSV
        assert config.data_file == "data/nifty.csv"

    def test_api_source_skips_csv_validation(self):
        config = BacktestConfig(
            data_source=DataSource.ZERODHA,
            data_file="not_a_csv",
        )
        assert config.data_file == "not_a_csv"

    def test_csv_source_still_validates_extension(self):
        with pytest.raises(Exception):
            BacktestConfig(
                data_source=DataSource.CSV,
                data_file="data.txt",
            )


class TestRiskConfig:

    def test_default_risk(self):
        risk = RiskConfig()
        assert risk.stop_loss_pct is None
        assert risk.max_position_size_pct == 1.0

    def test_invalid_stop_loss(self):
        with pytest.raises(Exception):
            RiskConfig(stop_loss_pct=-0.05)

    def test_invalid_position_size(self):
        with pytest.raises(Exception):
            RiskConfig(max_position_size_pct=1.5)
