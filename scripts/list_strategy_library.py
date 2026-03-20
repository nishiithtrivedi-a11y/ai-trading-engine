"""Print runnable and deferred strategy library summary."""

from __future__ import annotations

from collections import Counter
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.strategies.registry import (
    get_strategies_by_category,
    list_manifest_entries,
    list_strategy_keys,
    list_unsupported_strategies,
)


def main() -> None:
    runnable = list_strategy_keys()
    print(f"Runnable strategies: {len(runnable)}")

    print("\nRunnable by category:")
    for category, keys in get_strategies_by_category().items():
        print(f"- {category}: {len(keys)}")

    manifest_rows = list_manifest_entries()
    counts = Counter(row["classification"] for row in manifest_rows)
    print("\nManifest classifications:")
    for label in ("full", "limited", "deferred", "not_strategy_layer"):
        print(f"- {label}: {counts.get(label, 0)}")

    unsupported = list_unsupported_strategies()
    print(f"\nUnsupported/deferred rows: {len(unsupported)}")


if __name__ == "__main__":
    main()
