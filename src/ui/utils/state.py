"""
Session state management for the Streamlit dashboard.

Provides helpers for managing Streamlit session state without
tightly coupling page modules to st.session_state internals.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# State keys (centralized to avoid typos)
# ---------------------------------------------------------------------------

KEY_OUTPUT_DIR = "output_dir"
KEY_SELECTED_BACKTEST = "selected_backtest"
KEY_SELECTED_HORIZON = "selected_horizon"
KEY_LAST_REFRESH = "last_refresh"
KEY_RUN_HISTORY = "run_history"
KEY_LAST_RUN_RESULTS = "last_run_results"


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

    # ----- Run history (for Control Center) -----

    def get_run_history(self) -> List[Dict[str, Any]]:
        """Get the full run history list."""
        return self.get(KEY_RUN_HISTORY, [])

    def add_run_result(self, result_dict: Dict[str, Any]) -> None:
        """Append a run result to the history."""
        history: List[Dict[str, Any]] = self.get_run_history()
        entry = dict(result_dict)
        entry.setdefault("timestamp", datetime.now().isoformat())
        history.append(entry)
        self.set(KEY_RUN_HISTORY, history)

        # Also update last-run-per-engine map
        last_runs: Dict[str, Dict[str, Any]] = self.get(KEY_LAST_RUN_RESULTS, {})
        engine_name = entry.get("engine_name", "unknown")
        last_runs[engine_name] = entry
        self.set(KEY_LAST_RUN_RESULTS, last_runs)

    def get_last_run(self, engine_name: str) -> Optional[Dict[str, Any]]:
        """Get the most recent result for a specific engine."""
        last_runs: Dict[str, Dict[str, Any]] = self.get(KEY_LAST_RUN_RESULTS, {})
        return last_runs.get(engine_name)

    def get_all_last_runs(self) -> Dict[str, Dict[str, Any]]:
        """Get the last result for every engine."""
        return self.get(KEY_LAST_RUN_RESULTS, {})


def get_app_state() -> AppState:
    """Get the singleton AppState instance."""
    return AppState()
