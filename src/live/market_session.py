"""
Persistence helpers for live signal pipeline sessions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

from src.live.models import LIVE_SIGNAL_SCHEMA_VERSION, SessionSignalReport


@dataclass
class LiveSessionStore:
    output_dir: Path

    def __init__(self, output_dir: str | Path) -> None:
        self.output_dir = Path(output_dir)

    def export(
        self,
        report: SessionSignalReport,
        *,
        include_paper_handoff: bool = False,
    ) -> dict[str, Path]:
        self.output_dir.mkdir(parents=True, exist_ok=True)

        exports: dict[str, Path] = {}

        signals_path = self.output_dir / "signals.csv"
        self._write_signals_csv(report, signals_path)
        exports["signals"] = signals_path

        watchlist_path = self.output_dir / "watchlist.csv"
        self._write_watchlist_csv(report, watchlist_path)
        exports["watchlist"] = watchlist_path

        regime_path = self.output_dir / "regime_snapshot.csv"
        self._write_regime_csv(report, regime_path)
        exports["regime_snapshot"] = regime_path

        state_path = self.output_dir / "session_state.json"
        state_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
        exports["session_state"] = state_path

        summary_path = self.output_dir / "session_summary.md"
        summary_path.write_text(self._build_summary_markdown(report), encoding="utf-8")
        exports["session_summary"] = summary_path

        if include_paper_handoff:
            handoff_path = self.output_dir / "paper_handoff_signals.csv"
            self._write_paper_handoff_csv(report, handoff_path)
            exports["paper_handoff"] = handoff_path

        meta_path = self.output_dir / "live_artifacts_meta.json"
        self._write_artifacts_meta(report, exports, meta_path)
        exports["artifacts_meta"] = meta_path

        return exports

    @staticmethod
    def _write_signals_csv(report: SessionSignalReport, path: Path) -> None:
        rows = [decision.to_dict() for decision in report.decisions]
        if not rows:
            rows = [
                {
                    "symbol": "",
                    "timeframe": report.timeframe,
                    "strategy_name": "",
                    "signal": "",
                    "timestamp": "",
                    "close_price": "",
                    "decision_type": "",
                    "reason": "",
                    "regime_label": "",
                    "risk_allowed": "",
                    "paper_handoff_eligible": "",
                    "metadata": {},
                }
            ]
        pd.DataFrame(rows).to_csv(path, index=False)

    @staticmethod
    def _write_watchlist_csv(report: SessionSignalReport, path: Path) -> None:
        state = report.watchlist_state
        if state is None:
            pd.DataFrame(
                [
                    {
                        "session_label": report.session_label,
                        "provider_name": report.provider_name,
                        "universe_name": report.universe_name,
                        "timeframe": report.timeframe,
                        "symbol": "",
                        "loaded": False,
                        "ranked": False,
                    }
                ]
            ).to_csv(path, index=False)
            return

        loaded = set(state.loaded_symbols)
        ranked = set(state.ranked_symbols)
        symbols = list(dict.fromkeys(state.requested_symbols + state.loaded_symbols + state.ranked_symbols))
        rows = [
            {
                "session_label": state.session_label,
                "provider_name": state.provider_name,
                "universe_name": state.universe_name,
                "timeframe": state.timeframe,
                "symbol": symbol,
                "loaded": symbol in loaded,
                "ranked": symbol in ranked,
            }
            for symbol in symbols
        ]
        pd.DataFrame(rows).to_csv(path, index=False)

    @staticmethod
    def _write_regime_csv(report: SessionSignalReport, path: Path) -> None:
        rows = report.regime_snapshots or [
            {
                "symbol": "",
                "timestamp": "",
                "composite_regime": "",
                "trend_regime": "",
                "volatility_regime": "",
                "reason": "",
            }
        ]
        pd.DataFrame(rows).to_csv(path, index=False)

    @staticmethod
    def _write_paper_handoff_csv(report: SessionSignalReport, path: Path) -> None:
        rows = []
        for decision in report.paper_handoff_decisions:
            rows.append(
                {
                    "symbol": decision.symbol,
                    "timeframe": decision.timeframe,
                    "strategy_name": decision.strategy_name,
                    "signal": decision.signal,
                    "timestamp": decision.timestamp.isoformat(),
                    "close_price": decision.close_price,
                    "regime_label": decision.regime_label,
                    "reason": decision.reason,
                }
            )

        if not rows:
            rows = [
                {
                    "symbol": "",
                    "timeframe": report.timeframe,
                    "strategy_name": "",
                    "signal": "",
                    "timestamp": "",
                    "close_price": "",
                    "regime_label": "",
                    "reason": "",
                }
            ]

        pd.DataFrame(rows).to_csv(path, index=False)

    @staticmethod
    def _build_summary_markdown(report: SessionSignalReport) -> str:
        summary = report.to_dict()["summary"]
        rs_top: list[str] = []
        for row in report.relative_strength_rows[:5]:
            symbol = str(row.get("symbol", ""))
            score = row.get("rolling_strength_score")
            if symbol:
                rs_top.append(f"{symbol} ({score})")

        selected_strategies = sorted(
            {
                d.strategy_name
                for d in report.decisions
                if d.strategy_name and d.strategy_name != "n/a"
            }
        )

        lines = [
            "# Live Signal Pipeline Session Summary",
            "",
            f"- Generated at: {report.generated_at.isoformat()}",
            f"- Session label: {report.session_label or 'default'}",
            f"- Provider: {report.provider_name}",
            f"- Timeframe: {report.timeframe}",
            f"- Universe: {report.universe_name or 'custom_symbols'}",
            f"- Symbols evaluated: {summary['symbols_loaded']}",
            "",
            "## Regime Snapshot Summary",
            "",
        ]

        if report.regime_snapshots:
            regime_counts: dict[str, int] = {}
            for row in report.regime_snapshots:
                label = str(row.get("composite_regime", "unknown"))
                regime_counts[label] = regime_counts.get(label, 0) + 1
            for label, count in sorted(regime_counts.items()):
                lines.append(f"- {label}: {count}")
        else:
            lines.append("- No regime snapshots were generated")

        lines += [
            "",
            "## Relative-Strength Top Symbols",
            "",
        ]
        if rs_top:
            for item in rs_top:
                lines.append(f"- {item}")
        else:
            lines.append("- Relative-strength ranking not available")

        lines += [
            "",
            "## Strategy / Signal Summary",
            "",
            f"- Strategies selected: {', '.join(selected_strategies) if selected_strategies else 'none'}",
            f"- Generated actionable signals: {summary['actionable_signals']}",
            f"- No-trade decisions: {summary['no_trade_decisions']}",
            f"- Risk rejections: {summary['risk_rejections']}",
            f"- Paper-handoff eligible: {summary['paper_handoff_eligible']}",
            "",
            "## Safety",
            "",
            "- This run generated signals only.",
            "- No live broker orders were placed.",
            "- This phase does not submit, modify, or cancel live orders.",
        ]

        return "\n".join(lines)

    @staticmethod
    def _write_artifacts_meta(
        report: SessionSignalReport,
        exports: dict[str, Path],
        path: Path,
    ) -> None:
        payload = {
            "schema_version": LIVE_SIGNAL_SCHEMA_VERSION,
            "generated_at": report.generated_at.isoformat(),
            "source": "live.market_session_store",
            "provider_name": report.provider_name,
            "timeframe": report.timeframe,
            "artifacts": {
                name: {
                    "path": str(file_path),
                    "format": file_path.suffix.lstrip("."),
                }
                for name, file_path in exports.items()
            },
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
