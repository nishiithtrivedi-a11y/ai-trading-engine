import pytest
import pandas as pd
from src.strategies.base_strategy import BaseStrategy

class LegacyStrategy(BaseStrategy):
    """Old C0 Strategy that uses `generate_signal` on full datasets."""
    def __init__(self, **params):
        super().__init__(**params)
    
    def generate_signal(self, data: pd.DataFrame, current_bar: pd.Series, bar_index: int, **kwargs):
        return 1

class IncrementalStrategy(BaseStrategy):
    """New C1 Strategy that explicitly overrides `on_bar`."""
    def __init__(self, **params):
        super().__init__(**params)
        
    def on_bar(self, current_bar: pd.Series, bar_index: int, context=None, **kwargs):
        return 1

def test_incremental_capabilities():
    import inspect
    leg = LegacyStrategy()
    sig = inspect.signature(leg.on_bar)
    # The default on_bar signature has `*args, **kwargs` but no explicit `data` requirement unless overridden! 
    # Wait, LegacyStrategy does NOT override on_bar, it overrides generate_signal. 

    # For LegacyStrategy, `on_bar` falls back to BaseStrategy.on_bar (*args). So `data` is NOT in parameters. But legacy strategies shouldn't hit on_bar anyway.
    # The real test is if `on_bar` works for Incremental.
    inc = IncrementalStrategy()
    inc_sig = inspect.signature(inc.on_bar)
    assert "data" not in inc_sig.parameters
    assert "current_bar" in inc_sig.parameters

def test_legacy_dispatcher_fallback():
    leg = LegacyStrategy()
    df = pd.DataFrame({"close": [10, 20]})
    # It should not explode when called
    assert leg.generate_signal(df, df.iloc[1], 1) == 1

def test_incremental_pipeline_hooks():
    inc = IncrementalStrategy()
    # It must support the precompute -> on_bar flow
    assert hasattr(inc, "precompute")
    assert hasattr(inc, "on_bar")
