from __future__ import annotations

import json
from pathlib import Path

from src.runtime.output_manifest import write_output_manifest


def test_write_output_manifest_from_mapping(tmp_path: Path) -> None:
    artifacts = {
        "signals": tmp_path / "signals.csv",
        "session_state": tmp_path / "session_state.json",
    }

    for path in artifacts.values():
        path.write_text("x", encoding="utf-8")

    manifest_path = write_output_manifest(
        output_dir=tmp_path,
        run_mode="live_safe",
        provider_name="indian_csv",
        artifacts=artifacts,
        metadata={"cycle": 1},
    )

    assert manifest_path.exists()
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert raw["run_mode"] == "live_safe"
    assert raw["provider_name"] == "indian_csv"
    assert raw["metadata"]["cycle"] == 1
    assert len(raw["artifacts"]) == 2
    assert raw["safety_notes"]
