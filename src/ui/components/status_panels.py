"""
Status display components for the Control Center.

Shows run results, engine status, config summaries, and pipeline progress.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import streamlit as st

from src.ui.utils.runners import RunResult


# ---------------------------------------------------------------------------
# Single run result display
# ---------------------------------------------------------------------------

def run_status_card(result: RunResult) -> None:
    """Display the outcome of a single engine run."""
    if result.success:
        st.success(
            f"**{result.engine_name}** completed in "
            f"{result.duration_seconds:.1f}s  \n"
            f"{result.message}"
        )
    else:
        st.error(
            f"**{result.engine_name}** failed after "
            f"{result.duration_seconds:.1f}s  \n"
            f"{result.message}"
        )
        if result.error_details:
            with st.expander("Error details"):
                st.code(result.error_details, language="text")

    if result.artifacts:
        with st.expander("Output artifacts"):
            for name, path in result.artifacts.items():
                st.text(f"{name}: {path}")


# ---------------------------------------------------------------------------
# Run history panel
# ---------------------------------------------------------------------------

def run_history_panel(last_runs: Dict[str, Dict[str, Any]]) -> None:
    """Show the most recent run result for each engine."""
    if not last_runs:
        st.caption("No engines have been run yet this session.")
        return

    for engine_name, entry in last_runs.items():
        success = entry.get("success", False)
        icon = "OK" if success else "FAIL"
        ts = entry.get("timestamp", "")
        duration = entry.get("duration_seconds", 0)
        message = entry.get("message", "")

        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            if success:
                st.markdown(f"**[{icon}]** {engine_name}")
            else:
                st.markdown(f"**[{icon}]** {engine_name}")
        with col2:
            st.caption(f"{duration:.1f}s" if duration else "")
        with col3:
            st.caption(ts[:19] if ts else "")

        if message:
            st.caption(f"  {message}")

        st.divider()


# ---------------------------------------------------------------------------
# Config summary panel
# ---------------------------------------------------------------------------

def config_summary_panel(
    output_dir: str,
    provider_status: Dict[str, Any],
    realtime_status: Dict[str, Any],
    data_availability: Dict[str, bool],
) -> None:
    """Show a read-only summary of current config and data state."""
    st.subheader("Configuration Summary")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Provider", provider_status.get("default_provider", "csv"))
        st.metric("Output Dir", output_dir)

    with col2:
        rt_enabled = realtime_status.get("enabled", False)
        rt_mode = realtime_status.get("mode", "off")
        st.metric("Realtime", "Enabled" if rt_enabled else "Disabled")
        st.metric("RT Mode", rt_mode)

    with col3:
        total = len(data_availability)
        available = sum(1 for v in data_availability.values() if v)
        st.metric("Data Phases", f"{available}/{total}")
        st.metric("RT Max Cycles", realtime_status.get("max_cycles", "N/A"))


# ---------------------------------------------------------------------------
# Pipeline progress display
# ---------------------------------------------------------------------------

def pipeline_progress_panel(results: List[RunResult]) -> None:
    """Display step-by-step pipeline progress."""
    if not results:
        return

    for i, r in enumerate(results, 1):
        if r.success:
            st.success(
                f"Step {i}: **{r.engine_name}** "
                f"({r.duration_seconds:.1f}s)"
            )
        else:
            st.error(
                f"Step {i}: **{r.engine_name}** FAILED "
                f"({r.duration_seconds:.1f}s)"
            )
            if r.error_details:
                with st.expander(f"Error details for {r.engine_name}"):
                    st.code(r.error_details, language="text")
            st.warning("Pipeline stopped at this step.")
            break

    total_time = sum(r.duration_seconds for r in results)
    all_ok = all(r.success for r in results)

    if all_ok:
        st.info(
            f"Pipeline completed successfully: {len(results)} stages "
            f"in {total_time:.1f}s"
        )
    else:
        n_ok = sum(1 for r in results if r.success)
        st.warning(
            f"Pipeline partially completed: {n_ok}/{len(results)} stages "
            f"in {total_time:.1f}s"
        )
