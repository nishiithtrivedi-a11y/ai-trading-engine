"""
Session state management for the Streamlit dashboard.

Provides helpers for managing Streamlit session state without
tightly coupling page modules to st.session_state internals.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# State keys (centralized to avoid typos)
# ---------------------------------------------------------------------------

KEY_OUTPUT_DIR = "output_dir"
KEY_SELECTED_BACKTEST = "selected_backtest"
KEY_SELECTED_HORIZON = "selected_horizon"
KEY_LAST_REFRESH = "last_refresh"


# ---------------------------------------------------------------------------
# State accessor (works with or without Streamlit)
# ---------------------------------------------------------------------------

class AppState:
    """Thin wrapper around Streamlit session state.

    Falls back to an in-memory dict when Streamlit is not available
    (e.g., during testing).
    """

    def __init__(self) -> None:
        self._fallback: Dict[str, Any] = {}
        self._use_streamlit = False
        try:
            import streamlit as st
            # Only use streamlit state if we're actually in a streamlit context
            if hasattr(st, "session_state"):
                self._use_streamlit = True
        except ImportError:
            pass

    def _store(self) -> Dict[str, Any]:
        if self._use_streamlit:
            import streamlit as st
            return st.session_state
        return self._fallback

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from session state."""
        return self._store().get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a value in session state."""
        self._store()[key] = value

    def setdefault(self, key: str, default: Any) -> Any:
        """Set a default value if key is not present, return current value."""
        store = self._store()
        if key not in store:
            store[key] = default
        return store[key]

    def get_output_dir(self) -> str:
        """Get the configured output directory."""
        return self.get(KEY_OUTPUT_DIR, "output")

    def set_output_dir(self, path: str) -> None:
        """Set the output directory."""
        self.set(KEY_OUTPUT_DIR, path)

    def get_selected_backtest(self) -> Optional[str]:
        """Get the currently selected backtest run name."""
        return self.get(KEY_SELECTED_BACKTEST)

    def set_selected_backtest(self, name: str) -> None:
        """Set the currently selected backtest run name."""
        self.set(KEY_SELECTED_BACKTEST, name)

    def get_selected_horizon(self) -> str:
        """Get the currently selected decision horizon."""
        return self.get(KEY_SELECTED_HORIZON, "intraday")

    def set_selected_horizon(self, horizon: str) -> None:
        """Set the currently selected decision horizon."""
        self.set(KEY_SELECTED_HORIZON, horizon)


def get_app_state() -> AppState:
    """Get the singleton AppState instance."""
    return AppState()
