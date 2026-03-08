"""
Control Center page - run engines, view status, manage research pipeline.

This page transforms the dashboard from a read-only viewer into a
research control center with safe, bounded engine invocations.

Safety constraints:
- All engines use the CSV provider (no live API calls)
- No trade execution, no broker integration
- Realtime is limited to single simulated cycles
- All errors are caught and displayed, never crash the UI
"""

from __future__ import annotations

import streamlit as st

from src.ui.components.action_panels import (
    engine_action_button,
    pipeline_action_panel,
    realtime_action_panel,
)
from src.ui.components.status_panels import (
    config_summary_panel,
    run_history_panel,
)
from src.ui.utils.loaders import get_data_availability
from src.ui.utils.runners import (
    get_provider_status,
    get_realtime_config_status,
    run_decision_engine,
    run_market_intelligence,
    run_monitoring,
    run_research_lab,
    run_scanner,
)
from src.ui.utils.state import get_app_state


def render(output_dir: str) -> None:
    """Render the Control Center page."""
    st.header("Research Control Center")
    st.caption(
        "Run analysis engines, refresh data, and manage research pipelines. "
        "All actions are local, bounded, and research-only -- no live trades."
    )

    state = get_app_state()

    # ----- Config summary -----
    with st.expander("Configuration & Data Status", expanded=False):
        provider_status = get_provider_status()
        realtime_status = get_realtime_config_status()
        data_avail = get_data_availability(output_dir)
        config_summary_panel(output_dir, provider_status, realtime_status, data_avail)

        st.divider()
        st.caption("Data Availability")
        for phase, available in data_avail.items():
            label = phase.replace("_", " ").title()
            if available:
                st.success(f"{label} - data available")
            else:
                st.warning(f"{label} - no data yet")

    st.divider()

    # ----- Full pipeline (prominent, full-width) -----
    pipeline_action_panel(output_dir, state)

    st.divider()

    # ----- Individual engine buttons (three columns) -----
    st.subheader("Individual Engines")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("**Core Analysis**")

        engine_action_button(
            label="Run Scanner",
            engine_name="Scanner",
            runner_fn=run_scanner,
            output_dir=output_dir,
            state=state,
            description="Scan universe for opportunities (RSI + SMA strategies)",
        )

        st.divider()

        engine_action_button(
            label="Run Monitoring",
            engine_name="Monitoring",
            runner_fn=run_monitoring,
            output_dir=output_dir,
            state=state,
            description="Market regime, alerts, relative strength analysis",
        )

        st.divider()

        engine_action_button(
            label="Run Decision Engine",
            engine_name="Decision Engine",
            runner_fn=run_decision_engine,
            output_dir=output_dir,
            state=state,
            description="Runs monitoring + picks: intraday/swing/positional",
        )

    with col2:
        st.markdown("**Intelligence & Research**")

        engine_action_button(
            label="Run Market Intelligence",
            engine_name="Market Intelligence",
            runner_fn=run_market_intelligence,
            output_dir=output_dir,
            state=state,
            description="Breadth, sector rotation, volume, volatility regime",
        )

        st.divider()

        engine_action_button(
            label="Run Research Lab",
            engine_name="Research Lab",
            runner_fn=run_research_lab,
            output_dir=output_dir,
            state=state,
            description="Strategy discovery, scoring, and robustness analysis",
        )

    with col3:
        st.markdown("**Realtime**")

        realtime_action_panel(output_dir, state)

    st.divider()

    # ----- Refresh button -----
    st.subheader("Dashboard Refresh")
    if st.button(
        "Refresh Data Availability",
        key="btn_refresh_data",
        use_container_width=True,
    ):
        st.rerun()

    st.divider()

    # ----- Run history -----
    st.subheader("Run History (This Session)")
    run_history_panel(state.get_all_last_runs())


if __name__ == "__main__":
    from src.ui.utils.state import get_app_state

    render(get_app_state().get_output_dir())
