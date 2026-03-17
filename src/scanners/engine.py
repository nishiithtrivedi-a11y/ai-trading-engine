"""
Main scanner orchestrator for Phase 3 signal research.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from src.scanners.classifier import OpportunityClassifier
from src.scanners.config import ScannerConfig
from src.scanners.data_gateway import DataGateway
from src.scanners.models import Opportunity, ScanResult
from src.scanners.scorer import OpportunityScorer
from src.scanners.setup_engine import SetupEngine
from src.scanners.signal_runner import SignalRunner
from src.scanners.universe_resolver import UniverseResolver

if TYPE_CHECKING:
    from src.analysis.registry import AnalysisRegistry


class StockScannerEngineError(Exception):
    """Raised when scanner orchestration fails."""


@dataclass
class StockScannerEngine:
    scanner_config: ScannerConfig
    universe_resolver: Optional[UniverseResolver] = None
    data_gateway: Optional[DataGateway] = None
    signal_runner: Optional[SignalRunner] = None
    setup_engine: Optional[SetupEngine] = None
    classifier: Optional[OpportunityClassifier] = None
    scorer: Optional[OpportunityScorer] = None
    analysis_registry: Optional["AnalysisRegistry"] = None

    def __post_init__(self) -> None:
        self.universe_resolver = self.universe_resolver or UniverseResolver()
        self.data_gateway = self.data_gateway or DataGateway(
            provider_name=self.scanner_config.provider_name,
            data_dir=self.scanner_config.data_dir,
        )
        self.signal_runner = self.signal_runner or SignalRunner(
            min_required_bars=self.scanner_config.min_history_bars
        )
        self.setup_engine = self.setup_engine or SetupEngine()
        self.classifier = self.classifier or OpportunityClassifier()
        self.scorer = self.scorer or OpportunityScorer()

    def run(self, export: bool = False, exporter=None) -> ScanResult:
        if not self.scanner_config.strategy_specs:
            raise StockScannerEngineError("scanner_config.strategy_specs cannot be empty")

        symbols = self.universe_resolver.resolve(
            universe_name=self.scanner_config.universe_name,
            custom_universe_file=self.scanner_config.custom_universe_file,
        )

        opportunities: list[Opportunity] = []
        errors: list[str] = []

        enabled_specs = [s for s in self.scanner_config.strategy_specs if s.enabled]
        num_jobs = 0

        for symbol in symbols:
            for spec in enabled_specs:
                timeframes = self.scanner_config.get_effective_timeframes(spec)

                for timeframe in timeframes:
                    num_jobs += 1

                    try:
                        data_handler = self.data_gateway.load_data(symbol, timeframe)
                        signal = self.signal_runner.run_signal(
                            symbol=symbol,
                            timeframe=timeframe,
                            strategy_spec=spec,
                            data_handler=data_handler,
                        )

                        if not signal.is_actionable:
                            continue

                        setup = self.setup_engine.build_setup(
                            signal=signal,
                            data_handler=data_handler,
                            scanner_config=self.scanner_config,
                        )

                        opp_class = self.classifier.classify(timeframe, self.scanner_config)

                        score_components = self.scorer.score(
                            signal=signal,
                            setup=setup,
                            data_handler=data_handler,
                            scanner_config=self.scanner_config,
                            analysis_registry=self.analysis_registry,
                        )

                        opportunity = Opportunity.from_parts(
                            snapshot=signal,
                            setup=setup,
                            classification=opp_class,
                            score=float(score_components["score"]),
                            reasons=["actionable_buy_signal"],
                            metadata={
                                "risk_reward": setup.risk_reward_ratio,
                                "score_components": score_components,
                                "setup_extras": dict(setup.extras),
                                "signal_extras": dict(signal.extras),
                            },
                            score_components=score_components,
                        )
                        opportunities.append(opportunity)

                    except Exception as exc:  # noqa: BLE001
                        message = (
                            f"Scan job failed for symbol={symbol} timeframe={timeframe} "
                            f"strategy={spec.strategy_name}: {exc}"
                        )
                        if self.scanner_config.skip_on_data_error:
                            errors.append(message)
                            continue
                        raise StockScannerEngineError(message) from exc

        ranked = self.scorer.rank(opportunities)

        result = ScanResult(
            opportunities=ranked,
            universe_name=self.scanner_config.universe_name,
            provider_name=self.scanner_config.provider_name,
            num_symbols_scanned=len(symbols),
            num_jobs=num_jobs,
            num_errors=len(errors),
            errors=errors,
        )

        if export:
            if exporter is None:
                from src.scanners.exporter import ScanExporter

                exporter = ScanExporter()
            exporter.export_all(result, self.scanner_config.export, top_n=self.scanner_config.top_n)

        return result
