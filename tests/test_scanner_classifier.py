from __future__ import annotations

import pytest

from src.scanners.classifier import OpportunityClassifier
from src.scanners.models import OpportunityClass


@pytest.mark.parametrize("timeframe", ["1m", "5m", "15m"])
def test_intraday_timeframes(timeframe: str) -> None:
    classifier = OpportunityClassifier()
    assert classifier.classify(timeframe) == OpportunityClass.INTRADAY


def test_1h_is_swing() -> None:
    classifier = OpportunityClassifier()
    assert classifier.classify("1h") == OpportunityClass.SWING


def test_1d_is_positional() -> None:
    classifier = OpportunityClassifier()
    assert classifier.classify("1D") == OpportunityClass.POSITIONAL


def test_invalid_timeframe_raises() -> None:
    classifier = OpportunityClassifier()
    with pytest.raises(ValueError):
        classifier.classify("2h")
