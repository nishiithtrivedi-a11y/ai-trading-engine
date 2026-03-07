"""
AI Trading Engine - Research Dashboard

Main Streamlit application entry point.
Run with: streamlit run src/ui/app.py
"""

import streamlit as st

st.set_page_config(
    page_title="AI Trading Engine",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)

from src.ui.utils.loaders import get_data_availability, list_backtest_runs
from src.ui.utils.state import get_app_state

# Import pages
from src.ui.pages import (
    overview,
    backtests,
    optimization,
    walk_forward,
    monte_carlo,
    scanner,
    monitoring,
    decision_engine,
    realtime,
)

# ---------------------------------------------------------------------------
# Sidebar navigation
# ---------------------------------------------------------------------------

PAGES = {
    "Overview": overview,
    "Backtests": backtests,
    "Optimization": optimization,
    "Walk-Forward": walk_forward,
    "Monte Carlo": monte_carlo,
    "Scanner": scanner,
    "Monitoring": monitoring,
    "Decision Engine": decision_engine,
    "Realtime": realtime,
}


def main():
    state = get_app_state()

    with st.sidebar:
        st.title("AI Trading Engine")
        st.caption("Research Dashboard")
        st.divider()

        page_name = st.radio(
            "Navigation",
            list(PAGES.keys()),
            label_visibility="collapsed",
        )

        st.divider()

        # Output directory config
        output_dir = st.text_input(
            "Output Directory",
            value=state.get_output_dir(),
            help="Path to the output directory containing phase artifacts",
        )
        state.set_output_dir(output_dir)

        # Data availability summary
        st.divider()
        st.caption("Data Availability")
        avail = get_data_availability(output_dir)
        for phase, available in avail.items():
            label = phase.replace("_", " ").title()
            status = "Available" if available else "Missing"
            st.text(f"{'[OK]' if available else '[  ]'} {label}")

    # Render selected page
    page_module = PAGES[page_name]
    page_module.render(state.get_output_dir())


if __name__ == "__main__":
    main()
