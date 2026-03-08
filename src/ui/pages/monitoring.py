"""
Monitoring page - watchlists, alerts, regime, relative strength.
"""

from __future__ import annotations

import streamlit as st

from src.ui.components.filters import severity_filter
from src.ui.components.tables import alerts_table, data_table, key_value_table
from src.ui.utils.formatters import fmt_timestamp
from src.ui.utils.loaders import (
    load_monitoring_alerts,
    load_monitoring_regime,
    load_monitoring_relative_strength,
    load_monitoring_snapshot,
    load_monitoring_top_picks,
)


def render(output_dir: str) -> None:
    st.header("Market Monitoring")

    # Regime
    regime_data, regime_err = load_monitoring_regime(output_dir)
    if regime_data:
        st.subheader("Market Regime")
        rc1, rc2, rc3 = st.columns(3)
        with rc1:
            regime = regime_data.get("regime", "Unknown")
            st.metric("Regime", str(regime).title())
        with rc2:
            st.metric("Trend Score", regime_data.get("trend_score", "N/A"))
        with rc3:
            st.metric("Volatility Score", regime_data.get("volatility_score", "N/A"))

        reason = regime_data.get("reason")
        if reason:
            st.caption(f"Reason: {reason}")
    else:
        st.info("No regime data available. Run the monitoring engine first.")

    st.divider()

    # Top picks
    picks_df, picks_err = load_monitoring_top_picks(output_dir)
    if picks_df is not None:
        st.subheader("Top Picks")
        preferred = [
            "symbol", "timeframe", "strategy_name", "entry_price",
            "stop_loss", "target_price", "score", "horizon",
        ]
        available = [c for c in preferred if c in picks_df.columns]
        if available:
            st.dataframe(
                picks_df[available].head(20),
                use_container_width=True,
                hide_index=True,
            )
        else:
            data_table(picks_df, max_rows=20)
    else:
        st.info("No top picks available.")

    st.divider()

    # Alerts
    alerts_df, alerts_err = load_monitoring_alerts(output_dir)
    if alerts_df is not None:
        alerts_df = severity_filter(alerts_df, key="mon_severity_filter")
        alerts_table(alerts_df, title="Alerts")
    else:
        st.info("No alerts generated.")

    st.divider()

    # Relative strength
    rs_df, rs_err = load_monitoring_relative_strength(output_dir)
    if rs_df is not None:
        st.subheader("Relative Strength")
        sort_col = "score" if "score" in rs_df.columns else rs_df.columns[0]
        rs_sorted = rs_df.sort_values(sort_col, ascending=False) if sort_col == "score" else rs_df
        data_table(rs_sorted, max_rows=50)
    else:
        st.info("No relative strength data available.")

    # Snapshot metadata
    snap_data, _ = load_monitoring_snapshot(output_dir)
    if snap_data:
        st.divider()
        st.caption(f"Snapshot generated at: {fmt_timestamp(snap_data.get('generated_at'))}")


if __name__ == "__main__":
    from src.ui.utils.state import get_app_state

    render(get_app_state().get_output_dir())
