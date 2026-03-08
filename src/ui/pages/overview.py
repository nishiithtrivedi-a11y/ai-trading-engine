"""
Overview page - dashboard home with status summary.
"""

from __future__ import annotations

import streamlit as st

from src.ui.utils.loaders import (
    get_data_availability,
    list_backtest_runs,
    load_monitoring_regime,
    load_decision_summary,
    load_realtime_status,
    load_market_state,
)
from src.ui.utils.formatters import fmt_timestamp


def render(output_dir: str) -> None:
    st.header("AI Trading Engine - Overview")
    st.caption("Research and monitoring control room")

    avail = get_data_availability(output_dir)

    # Status cards
    st.subheader("Platform Status")
    cols = st.columns(4)

    total_available = sum(1 for v in avail.values() if v)
    total_phases = len(avail)

    with cols[0]:
        st.metric("Phases with Data", f"{total_available}/{total_phases}")
    with cols[1]:
        runs = list_backtest_runs(output_dir)
        st.metric("Backtest Runs", len(runs))
    with cols[2]:
        rt_data, _ = load_realtime_status(output_dir)
        rt_status = rt_data.get("status", "disabled") if rt_data else "disabled"
        st.metric("Realtime Status", rt_status.title())
    with cols[3]:
        regime_data, _ = load_monitoring_regime(output_dir)
        regime = regime_data.get("regime", "Unknown") if regime_data else "Unknown"
        st.metric("Market Regime", regime.title() if isinstance(regime, str) else str(regime))

    st.divider()

    # Market state
    market_data, market_err = load_market_state(output_dir)
    if market_data:
        st.subheader("Latest Market State")
        c1, c2, c3 = st.columns(3)
        ms = market_data.get("market_state", market_data)
        with c1:
            st.metric("Trend", str(ms.get("trend_state", "N/A")).title())
        with c2:
            st.metric("Risk Environment", str(ms.get("risk_environment", "N/A")).replace("_", " ").title())
        with c3:
            st.metric("Confidence", f"{ms.get('confidence_score', 'N/A')}")

        reasons = ms.get("summary_reasons", [])
        if reasons:
            with st.expander("Assessment Reasons"):
                for r in reasons:
                    st.write(f"- {r}")
    else:
        st.info("No market intelligence data available. Run the market intelligence engine to see market state.")

    st.divider()

    # Decision summary
    decision_data, decision_err = load_decision_summary(output_dir)
    if decision_data:
        st.subheader("Latest Decision Summary")
        summary = decision_data.get("summary", decision_data)
        total_selected = summary.get("selected_total", summary.get("total_selected", "N/A"))
        intraday = summary.get("intraday_total", summary.get("intraday_count", "N/A"))
        swing = summary.get("swing_total", summary.get("swing_count", "N/A"))
        positional = summary.get("positional_total", summary.get("positional_count", "N/A"))
        dc1, dc2, dc3, dc4 = st.columns(4)
        with dc1:
            st.metric("Total Picks", total_selected)
        with dc2:
            st.metric("Intraday", intraday)
        with dc3:
            st.metric("Swing", swing)
        with dc4:
            st.metric("Positional", positional)
    else:
        st.info("No decision engine output available. Run the decision engine to see picks.")

    st.divider()

    # Quick links
    st.subheader("Data Availability")
    for phase, available in avail.items():
        label = phase.replace("_", " ").title()
        if available:
            st.success(f"{label} - data available")
        else:
            st.warning(f"{label} - no data yet")


if __name__ == "__main__":
    from src.ui.utils.state import get_app_state

    render(get_app_state().get_output_dir())
