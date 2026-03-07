"""
Phase 4 market monitoring orchestrator.
"""

from __future__ import annotations

import copy
import os
import tempfile
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from src.monitoring.alert_engine import AlertEngine
from src.monitoring.config import MonitoringConfig
from src.monitoring.exporter import MonitoringExporter
from src.monitoring.models import (
    MarketSnapshot,
    MonitoringRunResult,
    RegimeAssessment,
    RegimeState,
    RelativeStrengthSnapshot,
    SectorStrengthSnapshot,
    Watchlist,
)
from src.monitoring.regime_detector import RegimeDetector
from src.monitoring.sector_strength import SectorStrengthAnalyzer
from src.monitoring.snapshot_engine import SnapshotEngine
from src.monitoring.watchlist_manager import WatchlistManager
from src.scanners.engine import StockScannerEngine


class MarketMonitorError(Exception):
    """Raised when monitoring orchestration fails."""


@dataclass
class MarketMonitor:
    config: MonitoringConfig
    scanner_engine: Optional[StockScannerEngine] = None
    watchlist_manager: Optional[WatchlistManager] = None
    regime_detector: Optional[RegimeDetector] = None
    sector_strength_analyzer: Optional[SectorStrengthAnalyzer] = None
    alert_engine: Optional[AlertEngine] = None
    snapshot_engine: Optional[SnapshotEngine] = None
    exporter: Optional[MonitoringExporter] = None

    def __post_init__(self) -> None:
        self.scanner_engine = self.scanner_engine or StockScannerEngine(self.config.scanner_config)
        self.watchlist_manager = self.watchlist_manager or WatchlistManager()
        self.regime_detector = self.regime_detector or RegimeDetector()
        self.sector_strength_analyzer = self.sector_strength_analyzer or SectorStrengthAnalyzer()
        self.alert_engine = self.alert_engine or AlertEngine()
        self.snapshot_engine = self.snapshot_engine or SnapshotEngine()
        self.exporter = self.exporter or MonitoringExporter()
        self._last_regime: Optional[RegimeState] = None

    def run(
        self,
        export: bool = False,
        watchlist_names: Optional[list[str]] = None,
    ) -> MonitoringRunResult:
        warnings: list[str] = []
        errors: list[str] = []

        watchlists = self._load_watchlists(warnings)
        scan_symbols = self._select_scan_symbols(watchlists, watchlist_names)

        scan_result = self._run_scan(scan_symbols, warnings)

        regime_assessment = self._detect_regime(scan_symbols, warnings)
        rs_rows, sector_rows = self._analyze_relative_strength(scan_symbols, warnings)

        alerts = self.alert_engine.generate(
            scan_result=scan_result,
            config=self.config.alerts,
            regime_assessment=regime_assessment,
            previous_regime=self._last_regime,
            relative_strength=rs_rows,
            watchlists=watchlists,
        )
        if regime_assessment is not None:
            self._last_regime = regime_assessment.regime

        snapshot = self.snapshot_engine.build_snapshot(
            scan_result=scan_result,
            config=self.config.snapshot,
            regime_assessment=regime_assessment,
            relative_strength=rs_rows,
            watchlists=watchlists,
        )

        run_result = MonitoringRunResult(
            scan_result=scan_result,
            regime_assessment=regime_assessment,
            relative_strength=rs_rows,
            sector_strength=sector_rows,
            alerts=alerts,
            snapshot=snapshot,
            warnings=warnings,
            errors=errors,
        )

        if export:
            outputs = self.exporter.export_all(run_result, self.config.export)
            run_result.exports = {k: str(v) for k, v in outputs.items()}

        return run_result

    def _load_watchlists(self, warnings: list[str]) -> dict[str, Watchlist]:
        definitions = self.config.get_enabled_watchlists()
        if not definitions:
            return {}

        try:
            return self.watchlist_manager.load_many(definitions)
        except Exception as exc:  # noqa: BLE001
            if self.config.continue_on_error:
                warnings.append(f"watchlist load failed: {exc}")
                return {}
            raise MarketMonitorError(f"Watchlist loading failed: {exc}") from exc

    def _select_scan_symbols(
        self,
        watchlists: dict[str, Watchlist],
        watchlist_names: Optional[list[str]],
    ) -> Optional[list[str]]:
        if not watchlists:
            return None

        selected_names = watchlist_names or list(watchlists.keys())
        symbols: list[str] = []
        for name in selected_names:
            if name not in watchlists:
                raise MarketMonitorError(f"Unknown watchlist '{name}'")
            symbols.extend(watchlists[name].symbols)

        deduped = list(dict.fromkeys(symbols))
        if not deduped:
            raise MarketMonitorError("Selected watchlists resolved to an empty symbol set")
        return deduped

    def _run_scan(self, symbols: Optional[list[str]], warnings: list[str]):
        if symbols is None:
            return self.scanner_engine.run(export=False)

        tmp_file_path = ""
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as tmp:
                tmp_file_path = tmp.name
                pd.DataFrame({"symbol": symbols}).to_csv(tmp_file_path, index=False)

            scan_cfg = copy.deepcopy(self.config.scanner_config)
            scan_cfg.universe_name = "custom"
            scan_cfg.custom_universe_file = tmp_file_path

            engine = StockScannerEngine(scanner_config=scan_cfg)
            return engine.run(export=False)
        except Exception as exc:  # noqa: BLE001
            if self.config.continue_on_error:
                warnings.append(f"scanner run failed: {exc}")
                # Return empty result from current scanner for downstream compatibility.
                return self.scanner_engine.run(export=False)
            raise MarketMonitorError(f"Scanner run failed: {exc}") from exc
        finally:
            if tmp_file_path and os.path.exists(tmp_file_path):
                os.remove(tmp_file_path)

    def _detect_regime(
        self,
        scan_symbols: Optional[list[str]],
        warnings: list[str],
    ) -> Optional[RegimeAssessment]:
        reference_symbol = None
        if scan_symbols:
            reference_symbol = scan_symbols[0]
        else:
            reference_symbol = self.config.regime.benchmark_symbol

        try:
            return self.regime_detector.detect_from_gateway(
                symbol=reference_symbol,
                data_gateway=self.scanner_engine.data_gateway,
                config=self.config.regime,
            )
        except Exception as exc:  # noqa: BLE001
            if self.config.continue_on_error:
                warnings.append(f"regime detection failed: {exc}")
                return None
            raise MarketMonitorError(f"Regime detection failed: {exc}") from exc

    def _analyze_relative_strength(
        self,
        scan_symbols: Optional[list[str]],
        warnings: list[str],
    ) -> tuple[list[RelativeStrengthSnapshot], list[SectorStrengthSnapshot]]:
        if not scan_symbols:
            return [], []

        sector_map = None
        if self.config.relative_strength.sector_map_file:
            try:
                sector_map = self.sector_strength_analyzer.load_sector_map(
                    self.config.relative_strength.sector_map_file
                )
            except Exception as exc:  # noqa: BLE001
                if self.config.continue_on_error:
                    warnings.append(f"sector map load failed: {exc}")
                    sector_map = None
                else:
                    raise

        try:
            return self.sector_strength_analyzer.analyze(
                symbols=scan_symbols,
                data_gateway=self.scanner_engine.data_gateway,
                config=self.config.relative_strength,
                sector_map=sector_map,
            )
        except Exception as exc:  # noqa: BLE001
            if self.config.continue_on_error:
                warnings.append(f"relative strength analysis failed: {exc}")
                return [], []
            raise MarketMonitorError(f"Relative strength analysis failed: {exc}") from exc
