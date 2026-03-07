"""Tests for UI dashboard state management."""

from src.ui.utils.state import AppState, get_app_state


class TestAppState:

    def test_get_default(self):
        state = AppState()
        assert state.get("nonexistent", "default") == "default"

    def test_set_and_get(self):
        state = AppState()
        state.set("key", "value")
        assert state.get("key") == "value"

    def test_setdefault_new_key(self):
        state = AppState()
        result = state.setdefault("new_key", 42)
        assert result == 42
        assert state.get("new_key") == 42

    def test_setdefault_existing_key(self):
        state = AppState()
        state.set("existing", "original")
        result = state.setdefault("existing", "new")
        assert result == "original"

    def test_output_dir_default(self):
        state = AppState()
        assert state.get_output_dir() == "output"

    def test_output_dir_custom(self):
        state = AppState()
        state.set_output_dir("/custom/path")
        assert state.get_output_dir() == "/custom/path"

    def test_selected_backtest(self):
        state = AppState()
        assert state.get_selected_backtest() is None
        state.set_selected_backtest("sma_crossover")
        assert state.get_selected_backtest() == "sma_crossover"

    def test_selected_horizon(self):
        state = AppState()
        assert state.get_selected_horizon() == "intraday"
        state.set_selected_horizon("swing")
        assert state.get_selected_horizon() == "swing"


class TestGetAppState:

    def test_returns_app_state(self):
        state = get_app_state()
        assert isinstance(state, AppState)
