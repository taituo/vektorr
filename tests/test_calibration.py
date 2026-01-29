"""
Tests for brain/calibration.py

Phase 0 validation metrics: Brier score, Log loss, CLV, ROI
"""

import math
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime
from brain.calibration import (
    CalibrationMetrics,
    CLVCalculator,
    ROICalculator,
    PredictionOutcome,
    ValidationReport,
)


class TestBrierScore:
    def test_perfect_predictions(self):
        """Perfect predictions should have Brier score of 0."""
        predictions = [1.0, 0.0, 1.0, 0.0]
        outcomes = [1, 0, 1, 0]
        brier = CalibrationMetrics.brier_score(predictions, outcomes)
        assert brier == 0.0

    def test_worst_predictions(self):
        """Completely wrong predictions should have Brier score of 1."""
        predictions = [0.0, 1.0, 0.0, 1.0]
        outcomes = [1, 0, 1, 0]
        brier = CalibrationMetrics.brier_score(predictions, outcomes)
        assert brier == 1.0

    def test_random_baseline(self):
        """Always predicting 0.5 should have Brier ~ 0.25."""
        predictions = [0.5] * 100
        outcomes = [1] * 50 + [0] * 50
        brier = CalibrationMetrics.brier_score(predictions, outcomes)
        assert abs(brier - 0.25) < 0.01

    def test_empty_inputs(self):
        """Empty inputs should return nan."""
        brier = CalibrationMetrics.brier_score([], [])
        assert math.isnan(brier)


class TestLogLoss:
    def test_confident_correct(self):
        """Confident correct predictions should have low log loss."""
        predictions = [0.99, 0.01, 0.99, 0.01]
        outcomes = [1, 0, 1, 0]
        ll = CalibrationMetrics.log_loss(predictions, outcomes)
        assert ll < 0.1

    def test_confident_wrong(self):
        """Confident wrong predictions should have high log loss."""
        predictions = [0.01, 0.99, 0.01, 0.99]
        outcomes = [1, 0, 1, 0]
        ll = CalibrationMetrics.log_loss(predictions, outcomes)
        assert ll > 2.0

    def test_uncertain(self):
        """Uncertain predictions (0.5) should have log loss ~ 0.693."""
        predictions = [0.5] * 4
        outcomes = [1, 0, 1, 0]
        ll = CalibrationMetrics.log_loss(predictions, outcomes)
        assert abs(ll - 0.693) < 0.01


class TestCalibrationBins:
    def test_perfect_calibration(self):
        """Well calibrated predictions should have matching actual rates."""
        # All 0.7 predictions with 70% actually occurring
        predictions = [0.7] * 10
        outcomes = [1, 1, 1, 1, 1, 1, 1, 0, 0, 0]
        bins = CalibrationMetrics.calibration_bins(predictions, outcomes, n_bins=10)

        # Should have one bin with predictions around 0.7
        assert len(bins) >= 1
        relevant_bin = [b for b in bins if 0.6 <= b['bin_center'] <= 0.75]
        assert len(relevant_bin) >= 1

    def test_empty_bins(self):
        """Should handle sparse data gracefully."""
        predictions = [0.1, 0.9]  # Only two very different predictions
        outcomes = [0, 1]
        bins = CalibrationMetrics.calibration_bins(predictions, outcomes, n_bins=10)
        assert len(bins) == 2  # Only 2 bins should have data


class TestCLVCalculator:
    def test_positive_clv(self):
        """Better than closing line should have positive CLV."""
        # Entry at 2.10, close at 1.90 -> beat the market
        clv = CLVCalculator.calculate_clv(2.10, 1.90)
        expected = (2.10 / 1.90) - 1
        assert abs(clv - expected) < 0.001
        assert clv > 0

    def test_negative_clv(self):
        """Worse than closing line should have negative CLV."""
        # Entry at 1.90, close at 2.10 -> market moved against us
        clv = CLVCalculator.calculate_clv(1.90, 2.10)
        assert clv < 0

    def test_zero_clv(self):
        """Same as closing line should have zero CLV."""
        clv = CLVCalculator.calculate_clv(2.00, 2.00)
        assert abs(clv) < 0.001

    def test_invalid_odds(self):
        """Invalid odds should return nan."""
        assert math.isnan(CLVCalculator.calculate_clv(0, 2.0))
        assert math.isnan(CLVCalculator.calculate_clv(2.0, 0))
        assert math.isnan(CLVCalculator.calculate_clv(-1, 2.0))


class TestROICalculator:
    def test_positive_roi(self):
        """Profitable bets should have positive ROI."""
        bets = [
            PredictionOutcome("m1", datetime.now(), 0.6, 1, 2.0, stake=10, pnl=10),
            PredictionOutcome("m2", datetime.now(), 0.6, 1, 2.0, stake=10, pnl=10),
            PredictionOutcome("m3", datetime.now(), 0.6, 0, 2.0, stake=10, pnl=-10),
        ]
        roi = ROICalculator.calculate_roi(bets)
        assert roi > 0  # +10 / 30 = +33%

    def test_negative_roi(self):
        """Losing bets should have negative ROI."""
        bets = [
            PredictionOutcome("m1", datetime.now(), 0.6, 0, 2.0, stake=10, pnl=-10),
            PredictionOutcome("m2", datetime.now(), 0.6, 0, 2.0, stake=10, pnl=-10),
            PredictionOutcome("m3", datetime.now(), 0.6, 1, 2.0, stake=10, pnl=10),
        ]
        roi = ROICalculator.calculate_roi(bets)
        assert roi < 0

    def test_sharpe_ratio(self):
        """Sharpe ratio should be calculable."""
        bets = [
            PredictionOutcome("m1", datetime.now(), 0.6, 1, 2.0, stake=10, pnl=10),
            PredictionOutcome("m2", datetime.now(), 0.6, 1, 2.0, stake=10, pnl=10),
            PredictionOutcome("m3", datetime.now(), 0.6, 0, 2.0, stake=10, pnl=-10),
            PredictionOutcome("m4", datetime.now(), 0.6, 1, 2.0, stake=10, pnl=10),
        ]
        sharpe = ROICalculator.sharpe_ratio(bets)
        assert not math.isnan(sharpe)
        assert sharpe > 0  # More wins than losses


class TestValidationReport:
    def test_exit_criteria_not_met(self):
        """Should fail exit criteria with insufficient data."""
        bets = [
            PredictionOutcome("m1", datetime.now(), 0.6, 1, 2.0, 1.9, stake=10, pnl=10),
        ]
        report = ValidationReport(bets)
        result = report.generate()

        assert result['total_bets'] == 1
        assert result['exit_criteria']['min_decisions_met'] == False
        assert result['exit_criteria']['all_passed'] == False

    def test_report_structure(self):
        """Report should have all expected fields."""
        bets = [
            PredictionOutcome("m1", datetime.now(), 0.6, 1, 2.0, 1.9, stake=10, pnl=10),
            PredictionOutcome("m2", datetime.now(), 0.4, 0, 2.0, 2.1, stake=10, pnl=-10),
        ]
        report = ValidationReport(bets)
        result = report.generate()

        # Check all expected keys exist
        expected_keys = [
            'brier_score', 'log_loss', 'ece',
            'clv_mean', 'roi', 'sharpe_ratio',
            'total_bets', 'exit_criteria'
        ]
        for key in expected_keys:
            assert key in result, f"Missing key: {key}"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
