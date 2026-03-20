from __future__ import annotations

from src.strategies.registry import (
    get_runtime_strategy_registry,
    load_strategy_manifest,
    list_manifest_entries,
)


def test_strategy_manifest_has_expected_total_and_classifications() -> None:
    manifest = load_strategy_manifest()
    assert manifest["summary"]["total"] == 250

    rows = manifest["strategies"]
    assert len(rows) == 250

    allowed = {"full", "limited", "deferred", "not_strategy_layer"}
    for row in rows:
        assert row["classification"] in allowed


def test_manifest_strategy_ids_are_unique() -> None:
    rows = load_strategy_manifest()["strategies"]
    ids = [row["strategy_id"] for row in rows]
    assert len(ids) == len(set(ids))


def test_runnable_manifest_rows_map_to_runtime_registry() -> None:
    runtime_registry = get_runtime_strategy_registry()
    runnable_rows = [r for r in list_manifest_entries() if r["runnable"]]
    assert runnable_rows, "expected at least one runnable strategy in manifest"

    for row in runnable_rows:
        impl = row.get("implementation")
        assert impl is not None
        key = impl.get("registry_key")
        assert key in runtime_registry


def test_manifest_summary_matches_row_counts() -> None:
    manifest = load_strategy_manifest()
    rows = manifest["strategies"]

    counts = {
        key: sum(1 for row in rows if row["classification"] == key)
        for key in ("full", "limited", "deferred", "not_strategy_layer")
    }
    summary = manifest["summary"]

    assert summary["full"] == counts["full"]
    assert summary["limited"] == counts["limited"]
    assert summary["deferred"] == counts["deferred"]
    assert summary["not_strategy_layer"] == counts["not_strategy_layer"]
    assert summary["runnable_total"] == counts["full"] + counts["limited"]

