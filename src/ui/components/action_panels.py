"""
Action button components for the Control Center.

Provides reusable button panels that trigger engine runners
and update session state with results.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

import streamlit as st

from src.ui.components.status_panels import (
    pipeline_progress_panel,
    run_status_card,
)
from src.ui.utils.runners import (
    RunResult,
    get_realtime_config_status,
    run_decision_engine,
    run_full_pipeline,
    run_market_intelligence,
    run_monitoring,
    run_realtime_once,
    run_research_lab,
    run_scanner,
)
from src.ui.utils.state import AppState


# ---------------------------------------------------------------------------
# Generic engine action button
# ---------------------------------------------------------------------------

def engine_action_button(
    label: str,
    engine_name: str,
    runner_fn: Callable[..., RunResult],
    output_dir: str,
    state: AppState,
    description: str = "",
    button_key: Optional[str] = None,
    **runner_kwargs: Any,
) -> Optional[RunResult]:
    """Render a button that triggers an engine runner.

    Parameters
    ----------
    label : str
        Button label text.
    engine_name : str
        Display name used for status tracking.
    runner_fn : callable
        The runner function to call (from runners.py).
    output_dir : str
        Output directory to pass to the runner.
    state : AppState
        Session state for recording results.
    description : str
        Short help text shown below the button.
    button_key : str, optional
        Unique Streamlit widget key.
    **runner_kwargs
        Extra keyword arguments passed to runner_fn.

    Returns
    -------
    RunResult or None
        The run result if the button was clicked, else None.
    """
    key = button_key or f"btn_{engine_name.lower().replace(' ', '_')}"

    if description:
        st.caption(description)

    if st.button(label, key=key, use_container_width=True):
        with st.spinner(f"Running {engine_name}..."):
            result = runner_fn(output_dir, **runner_kwargs)

        run_status_card(result)
        state.add_run_result(result.to_dict())
        return result

    # Show last run status if available
    last = state.get_last_run(engine_name)
    if last:
        success = last.get("success", False)
        ts = last.get("timestamp", "")[:19]
        dur = last.get("duration_seconds", 0)
        if success:
            st.caption(f"Last run: OK ({dur:.1f}s) at {ts}")
        else:
            st.caption(f"Last run: FAILED ({dur:.1f}s) at {ts}")

    return None


# ---------------------------------------------------------------------------
# Pipeline action panel
# ---------------------------------------------------------------------------

def pipeline_action_panel(
    output_dir: str,
    state: AppState,
) -> Optional[list]:
    """Full research pipeline button with stage progress."""
    st.subheader("Full Research Pipeline")
    st.caption(
        "Runs: Market Intelligence > Scanner > Monitoring > Decision Engine"
    )

    if st.button(
        "Run Full Pipeline",
        key="btn_full_pipeline",
        use_container_width=True,
        type="primary",
    ):
        progress_bar = st.progress(0.0)
        status_text = st.empty()

        def on_progress(name: str, idx: int, total: int) -> None:
            pct = idx / total
            progress_bar.progress(pct)
            status_text.text(f"Running {name} ({idx + 1}/{total})...")

        with st.spinner("Running full research pipeline..."):
            results = run_full_pipeline(
                output_dir, progress_callback=on_progress
            )

        progress_bar.progress(1.0)
        status_text.text("Pipeline finished.")

        pipeline_progress_panel(results)

        # Record each result in state
        for r in results:
            state.add_run_result(r.to_dict())

        return results

    # Show last pipeline results summary
    last_runs = state.get_all_last_runs()
    pipeline_engines = [
        "Market Intelligence", "Scanner", "Monitoring", "Decision Engine"
    ]
    has_any = any(e in last_runs for e in pipeline_engines)
    if has_any:
        cols = st.columns(len(pipeline_engines))
        for i, name in enumerate(pipeline_engines):
            with cols[i]:
                last = last_runs.get(name)
                if last:
                    ok = last.get("success", False)
                    st.caption(f"{'OK' if ok else 'FAIL'}: {name}")
                else:
                    st.caption(f"--: {name}")

    return None


# ---------------------------------------------------------------------------
# Realtime action panel
# ---------------------------------------------------------------------------

def realtime_action_panel(
    output_dir: str,
    state: AppState,
) -> Optional[RunResult]:
    """Realtime engine panel with config status and single-cycle button."""
    st.subheader("Realtime Engine")

    # Show realtime config status
    rt_status = get_realtime_config_status()
    rt_enabled = rt_status.get("enabled", False)
    rt_mode = rt_status.get("mode", "off")

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Config Status", "Enabled" if rt_enabled else "Disabled")
    with col2:
        st.metric("Config Mode", rt_mode)

    st.caption(
        "Runs a single simulated cycle (max_cycles=1, mode=simulated). "
        "Safe and bounded — does not start an infinite loop."
    )

    if st.button(
        "Run One Realtime Cycle",
        key="btn_realtime_once",
        use_container_width=True,
    ):
        with st.spinner("Running realtime cycle..."):
            result = run_realtime_once(output_dir)

        run_status_card(result)
        state.add_run_result(result.to_dict())
        return result

    last = state.get_last_run("Realtime (Single Cycle)")
    if last:
        ok = last.get("success", False)
        ts = last.get("timestamp", "")[:19]
        st.caption(f"Last cycle: {'OK' if ok else 'FAIL'} at {ts}")

    return None
