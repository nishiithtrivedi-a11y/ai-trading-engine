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

from src.ui.utils.loaders import get_data_availability
from src.ui.utils.state import get_app_state

# Import pages
from src.ui.pages import (
    overview,
    control_center,
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
    "Control Center": control_center,
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
            st.text(f"{'[OK]' if available else '[  ]'} {label}")

    # Render selected page with explicit UI-level error handling so the app
    # does not silently blank on page exceptions.
    page_module = PAGES[page_name]
    try:
        render_fn = getattr(page_module, "render", None)
        if not callable(render_fn):
            st.error(f"Selected page '{page_name}' is missing a callable render() function.")
            return
        render_fn(state.get_output_dir())
    except Exception as exc:  # noqa: BLE001
        st.error(f"Failed to render page '{page_name}': {exc}")
        st.exception(exc)


if __name__ == "__main__":
    main()
