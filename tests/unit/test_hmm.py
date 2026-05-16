"""Unit tests for HMM regime detector."""
import pytest
from arb.models.hmm import RegimeDetector


def test_regime_fit_synthetic():
    detector = RegimeDetector()
    detector.fit_synthetic()
    regime = detector.current_regime()
    assert regime in (0, 1, 2)


def test_regime_labels():
    detector = RegimeDetector()
    detector.fit_synthetic()
    # After fitting on low/med/high vol segments, regime should be valid
    assert detector._fitted is True
    assert len(detector._regime_labels) == 3
