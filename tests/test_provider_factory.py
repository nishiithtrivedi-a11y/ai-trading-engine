"""Tests for provider factory."""

import pytest

from src.data.provider_config import DataProvidersConfig, ProviderEntry
from src.data.provider_factory import ProviderError, ProviderFactory


class TestProviderFactory:

    def _make_config(self, **providers) -> DataProvidersConfig:
        entries = {
            name: ProviderEntry(**settings)
            for name, settings in providers.items()
        }
        return DataProvidersConfig(
            default_provider="csv",
            providers=entries,
        )

    def test_create_unknown_provider_raises(self):
        config = self._make_config(csv={"enabled": True})
        factory = ProviderFactory(config)
        with pytest.raises(ProviderError, match="Unknown provider"):
            factory.create("nonexistent")

    def test_create_disabled_provider_raises(self):
        config = self._make_config(zerodha={"enabled": False})
        factory = ProviderFactory(config)
        with pytest.raises(ProviderError, match="disabled"):
            factory.create("zerodha")

    def test_create_zerodha_without_credentials_raises(self):
        config = self._make_config(
            zerodha={"enabled": True, "api_key": "", "api_secret": "", "access_token": ""}
        )
        factory = ProviderFactory(config)
        with pytest.raises(ProviderError, match="credentials"):
            factory.create("zerodha")

    def test_create_upstox_without_credentials_raises(self):
        config = self._make_config(
            upstox={"enabled": True, "api_key": "", "api_secret": "", "access_token": ""}
        )
        factory = ProviderFactory(config)
        with pytest.raises(ProviderError, match="credentials"):
            factory.create("upstox")

    def test_create_zerodha_with_credentials(self):
        config = self._make_config(
            zerodha={
                "enabled": True,
                "api_key": "key",
                "api_secret": "secret",
                "access_token": "token",
            }
        )
        factory = ProviderFactory(config)
        source = factory.create("zerodha")
        from src.data.sources import ZerodhaDataSource
        assert isinstance(source, ZerodhaDataSource)

    def test_create_upstox_with_credentials(self):
        config = self._make_config(
            upstox={
                "enabled": True,
                "api_key": "key",
                "api_secret": "secret",
                "access_token": "token",
            }
        )
        factory = ProviderFactory(config)
        source = factory.create("upstox")
        from src.data.sources import UpstoxDataSource
        assert isinstance(source, UpstoxDataSource)

    def test_create_indian_csv(self):
        config = self._make_config(indian_csv={"enabled": True})
        factory = ProviderFactory(config)
        source = factory.create("indian_csv", data_file="data/sample_data.csv")
        from src.data.indian_data_loader import IndianCSVDataSource
        assert isinstance(source, IndianCSVDataSource)

    def test_create_default_provider(self):
        config = self._make_config(csv={"enabled": True})
        factory = ProviderFactory(config)
        # Should use default_provider="csv"
        source = factory.create(data_file="data/sample_data.csv")
        from src.data.indian_data_loader import IndianCSVDataSource
        assert isinstance(source, IndianCSVDataSource)

    def test_list_providers(self):
        config = self._make_config(
            csv={"enabled": True},
            zerodha={"enabled": False},
        )
        factory = ProviderFactory(config)
        result = factory.list_providers()
        assert result == {"csv": True, "zerodha": False}

    def test_register_custom_provider(self):
        from src.data.base import BaseDataSource
        import pandas as pd

        class CustomSource(BaseDataSource):
            def load(self):
                return pd.DataFrame()

        ProviderFactory.register("custom_test", CustomSource)
        assert "custom_test" in ProviderFactory._registry

        # Clean up
        del ProviderFactory._registry["custom_test"]
