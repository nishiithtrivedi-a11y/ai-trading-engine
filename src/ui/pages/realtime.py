"""
Realtime page - view realtime engine status, cycle history, and alerts.
"""

from __future__ import annotations

import streamlit as st

from src.ui.components.tables import alerts_table, data_table, key_value_table
from src.ui.utils.formatters import fmt_timestamp
from src.ui.utils.loaders import (
    load_realtime_alerts,
    load_realtime_cycle_history,
    load_realtime_snapshot,
    load_realtime_status,
)


def render(output_dir: str) -> None:
    st.header("Realtime Engine")

    status_data, status_err = load_realtime_status(output_dir)

    if status_data is None:
        st.info(
            "Realtime engine has not run yet.\n\n"
            "The realtime engine is disabled by default. "
            "Enable it in config/realtime.yaml and run the realtime engine. "
            "See the README for usage examples."
        )
        return

    # Status overview
    st.subheader("Engine Status")
    cols = st.columns(4)
    with cols[0]:
        status = status_data.get("status", "unknown")
        st.metric("Status", status.title())
    with cols[1]:
        mode = status_data.get("mode", "off")
        st.metric("Mode", str(mode).title())
    with cols[2]:
        enabled = status_data.get("enabled", False)
        st.metric("Enabled", "Yes" if enabled else "No")
    with cols[3]:
        summary = status_data.get("summary", {})
        st.metric("Total Cycles", summary.get("total_cycles", "N/A"))

    # Cycle summary
    if summary:
        sc1, sc2, sc3 = st.columns(3)
        with sc1:
            st.metric("Completed", summary.get("completed_cycles", "N/A"))
        with sc2:
            st.metric("Skipped", summary.get("skipped_cycles", "N/A"))
        with sc3:
            st.metric("Failed", summary.get("failed_cycles", "N/A"))

    st.divider()

    # Cycle history
    history_df, history_err = load_realtime_cycle_history(output_dir)
    if history_df is not None:
        st.subheader("Cycle History")
        data_table(history_df, max_rows=50)
    else:
        st.info("No cycle history available.")

    st.divider()

    # Latest snapshot
    snapshot, snap_err = load_realtime_snapshot(output_dir)
    if snapshot:
        st.subheader("Latest Snapshot")
        st.caption(f"Generated at: {fmt_timestamp(snapshot.get('generated_at'))}")

        mon_summary = snapshot.get("monitoring_summary", {})
        if mon_summary:
            key_value_table(mon_summary, title="Monitoring Summary")

        dec_summary = snapshot.get("decision_summary", {})
        if dec_summary:
            key_value_table(dec_summary, title="Decision Summary")

        top_picks = snapshot.get("top_picks", [])
        if top_picks:
            import pandas as pd
            st.subheader("Snapshot Top Picks")
            st.dataframe(
                pd.DataFrame(top_picks),
                use_container_width=True,
                hide_index=True,
            )
    else:
        st.info("No realtime snapshot available.")

    st.divider()

    # Realtime alerts
    alerts_df, alerts_err = load_realtime_alerts(output_dir)
    if alerts_df is not None:
        alerts_table(alerts_df, title="Realtime Alerts")
    else:
        st.info("No realtime alerts available.")


if __name__ == "__main__":
    from src.ui.utils.state import get_app_state

    render(get_app_state().get_output_dir())
