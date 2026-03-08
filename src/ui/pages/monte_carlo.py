"""
Monte Carlo page - view robustness simulation results.
"""

from __future__ import annotations

import streamlit as st

from src.ui.components.filters import backtest_run_selector
from src.ui.components.tables import key_value_table
from src.ui.utils.formatters import fmt_currency, fmt_pct
from src.ui.utils.loaders import list_backtest_runs, load_monte_carlo_results


def render(output_dir: str) -> None:
    st.header("Monte Carlo Analysis")

    runs = list_backtest_runs(output_dir)
    mc_runs = [r for r in runs if any(
        k in r.lower() for k in ["monte", "mc", "carlo"]
    )]

    if not mc_runs and runs:
        mc_runs = runs

    if not mc_runs:
        st.info(
            "No Monte Carlo output found. Run a Monte Carlo analysis first.\n\n"
            "Example: `python run_rsi_monte_carlo.py`"
        )
        return

    selected = backtest_run_selector(mc_runs, key="mc_run_selector")
    if not selected:
        return

    st.divider()

    data, err = load_monte_carlo_results(selected, output_dir)
    if data is None:
        st.info(err or "No Monte Carlo results found.")
        return

    # Summary
    summary = data.get("summary", {})
    if summary:
        st.subheader("Simulation Summary")
        cols = st.columns(4)
        with cols[0]:
            prob = summary.get("probability_of_profit")
            st.metric("Prob. of Profit", fmt_pct(prob) if prob else "N/A")
        with cols[1]:
            st.metric("Median Final Equity", fmt_currency(
                summary.get("median_final_equity"), decimals=0
            ))
        with cols[2]:
            st.metric("Worst Case", fmt_currency(
                summary.get("worst_case_final_equity"), decimals=0
            ))
        with cols[3]:
            st.metric("Best Case", fmt_currency(
                summary.get("best_case_final_equity"), decimals=0
            ))

    st.divider()

    # Percentile tables
    percentiles = data.get("percentiles", {})
    if percentiles:
        st.subheader("Percentile Analysis")

        for metric_name, pctiles in percentiles.items():
            if isinstance(pctiles, dict):
                display_name = metric_name.replace("_", " ").title()
                st.write(f"**{display_name}**")
                pct_cols = st.columns(5)
                ordered_keys = ["p5", "p25", "p50", "p75", "p95"]
                labels = ["5th %ile", "25th %ile", "Median", "75th %ile", "95th %ile"]
                for i, (pk, label) in enumerate(zip(ordered_keys, labels)):
                    val = pctiles.get(pk, pctiles.get(str(pk)))
                    with pct_cols[i]:
                        if val is not None:
                            if "pct" in metric_name or "return" in metric_name:
                                st.metric(label, fmt_pct(val))
                            else:
                                st.metric(label, fmt_currency(val, decimals=0))
                        else:
                            st.metric(label, "N/A")
                st.write("")

    # Simulation config
    config_keys = ["num_simulations", "simulation_mode", "seed", "initial_capital"]
    config_data = {k: data.get(k) for k in config_keys if data.get(k) is not None}
    if config_data:
        st.divider()
        key_value_table(config_data, title="Simulation Configuration")


if __name__ == "__main__":
    from src.ui.utils.state import get_app_state

    render(get_app_state().get_output_dir())
