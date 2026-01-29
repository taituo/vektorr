"""
Calibration metrics for model validation.

Phase 0 - Validointi: Todista että logiikka tuottaa mitattavaa edgeä.

Metrics:
- Brier Score: Calibration accuracy (lower = better, 0 = perfect)
- Log Loss: Probabilistic prediction quality
- Calibration Plot Data: Predicted vs actual probabilities per bin
- CLV (Closing Line Value): Edge measurement
"""

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict
from datetime import datetime


@dataclass
class PredictionOutcome:
    """Single prediction with outcome for calibration."""
    match_id: str
    timestamp: datetime
    p_model: float          # predicted probability
    outcome: int            # 1 = event occurred, 0 = did not
    odds_at_decision: float
    odds_at_close: Optional[float] = None
    market: str = "NEXT_GOAL"
    selection: str = ""
    stake: float = 0.0
    pnl: float = 0.0


class CalibrationMetrics:
    """
    Calculates calibration metrics for model validation.

    Usage:
        metrics = CalibrationMetrics()
        brier = metrics.brier_score(predictions, outcomes)
        calibration_data = metrics.calibration_bins(predictions, outcomes)
        log_loss = metrics.log_loss(predictions, outcomes)
    """

    @staticmethod
    def brier_score(predictions: List[float], outcomes: List[int]) -> float:
        """
        Brier Score = (1/N) * sum((p_i - o_i)^2)

        Measures calibration accuracy.
        - Range: 0 to 1
        - Lower is better
        - 0 = perfect calibration
        - 0.25 = random baseline (always predicting 0.5)

        Args:
            predictions: List of predicted probabilities [0, 1]
            outcomes: List of actual outcomes (0 or 1)

        Returns:
            Brier score (float)
        """
        if not predictions or len(predictions) != len(outcomes):
            return float('nan')

        n = len(predictions)
        squared_errors = [(p - o) ** 2 for p, o in zip(predictions, outcomes)]
        return sum(squared_errors) / n

    @staticmethod
    def log_loss(predictions: List[float], outcomes: List[int], eps: float = 1e-15) -> float:
        """
        Log Loss = -1/N * sum(y*log(p) + (1-y)*log(1-p))

        Measures probabilistic prediction quality.
        - Lower is better
        - Heavily penalizes confident wrong predictions

        Args:
            predictions: List of predicted probabilities [0, 1]
            outcomes: List of actual outcomes (0 or 1)
            eps: Small value to avoid log(0)

        Returns:
            Log loss (float)
        """
        if not predictions or len(predictions) != len(outcomes):
            return float('nan')

        n = len(predictions)
        total = 0.0

        for p, y in zip(predictions, outcomes):
            # Clip probabilities to avoid log(0)
            p_clipped = max(eps, min(1 - eps, p))
            total += y * math.log(p_clipped) + (1 - y) * math.log(1 - p_clipped)

        return -total / n

    @staticmethod
    def calibration_bins(
        predictions: List[float],
        outcomes: List[int],
        n_bins: int = 10
    ) -> List[Dict]:
        """
        Groups predictions into bins and calculates actual rate per bin.

        Used for calibration plots: predicted probability vs actual frequency.

        Args:
            predictions: List of predicted probabilities [0, 1]
            outcomes: List of actual outcomes (0 or 1)
            n_bins: Number of bins (default 10)

        Returns:
            List of dicts with bin_center, mean_predicted, actual_rate, count
        """
        if not predictions or len(predictions) != len(outcomes):
            return []

        bin_edges = [i / n_bins for i in range(n_bins + 1)]
        results = []

        for i in range(n_bins):
            low, high = bin_edges[i], bin_edges[i + 1]

            # Get predictions in this bin
            bin_mask = [(low <= p < high) or (i == n_bins - 1 and p == high)
                       for p in predictions]
            bin_preds = [p for p, m in zip(predictions, bin_mask) if m]
            bin_outs = [o for o, m in zip(outcomes, bin_mask) if m]

            if bin_preds:
                results.append({
                    'bin_low': low,
                    'bin_high': high,
                    'bin_center': (low + high) / 2,
                    'mean_predicted': sum(bin_preds) / len(bin_preds),
                    'actual_rate': sum(bin_outs) / len(bin_outs),
                    'count': len(bin_preds),
                    'calibration_error': abs(sum(bin_preds) / len(bin_preds) - sum(bin_outs) / len(bin_outs))
                })

        return results

    @staticmethod
    def expected_calibration_error(
        predictions: List[float],
        outcomes: List[int],
        n_bins: int = 10
    ) -> float:
        """
        Expected Calibration Error (ECE).

        Weighted average of calibration errors across bins.
        ECE = sum(|bin_count/total| * |accuracy - confidence|)

        Args:
            predictions: List of predicted probabilities [0, 1]
            outcomes: List of actual outcomes (0 or 1)
            n_bins: Number of bins

        Returns:
            ECE (float), lower is better
        """
        bins = CalibrationMetrics.calibration_bins(predictions, outcomes, n_bins)
        if not bins:
            return float('nan')

        total = sum(b['count'] for b in bins)
        if total == 0:
            return float('nan')

        ece = sum((b['count'] / total) * b['calibration_error'] for b in bins)
        return ece


class CLVCalculator:
    """
    Closing Line Value (CLV) calculator.

    CLV = (entry_odds / closing_odds) - 1

    Positive CLV = beat the closing line (edge indicator)
    Negative CLV = worse than closing line
    """

    @staticmethod
    def calculate_clv(entry_odds: float, closing_odds: float) -> float:
        """
        Calculate CLV for a single bet.

        CLV = (entry_odds / closing_odds) - 1

        Example:
            Entry: 2.10, Close: 1.90 -> CLV = (2.10/1.90) - 1 = +10.5%
            Entry: 1.90, Close: 2.10 -> CLV = (1.90/2.10) - 1 = -9.5%

        Args:
            entry_odds: Odds at time of decision/bet
            closing_odds: Odds at market close (typically 2-5 min before event)

        Returns:
            CLV as decimal (0.05 = 5% edge)
        """
        if closing_odds <= 0 or entry_odds <= 0:
            return float('nan')
        return (entry_odds / closing_odds) - 1

    @staticmethod
    def mean_clv(bets: List[PredictionOutcome]) -> float:
        """
        Calculate mean CLV across all bets with closing odds.

        Args:
            bets: List of PredictionOutcome with odds_at_decision and odds_at_close

        Returns:
            Mean CLV (float)
        """
        clvs = []
        for bet in bets:
            if bet.odds_at_close and bet.odds_at_close > 0:
                clv = CLVCalculator.calculate_clv(bet.odds_at_decision, bet.odds_at_close)
                if not math.isnan(clv):
                    clvs.append(clv)

        if not clvs:
            return float('nan')
        return sum(clvs) / len(clvs)

    @staticmethod
    def clv_breakdown(bets: List[PredictionOutcome]) -> Dict:
        """
        Detailed CLV breakdown.

        Returns:
            Dict with mean, median, positive_pct, count
        """
        clvs = []
        for bet in bets:
            if bet.odds_at_close and bet.odds_at_close > 0:
                clv = CLVCalculator.calculate_clv(bet.odds_at_decision, bet.odds_at_close)
                if not math.isnan(clv):
                    clvs.append(clv)

        if not clvs:
            return {
                'mean': float('nan'),
                'median': float('nan'),
                'positive_pct': float('nan'),
                'count': 0,
                'std': float('nan')
            }

        clvs_sorted = sorted(clvs)
        n = len(clvs)
        mean = sum(clvs) / n
        median = clvs_sorted[n // 2] if n % 2 == 1 else (clvs_sorted[n // 2 - 1] + clvs_sorted[n // 2]) / 2
        positive_pct = len([c for c in clvs if c > 0]) / n

        # Standard deviation
        variance = sum((c - mean) ** 2 for c in clvs) / n
        std = math.sqrt(variance)

        return {
            'mean': mean,
            'median': median,
            'positive_pct': positive_pct,
            'count': n,
            'std': std
        }


class ROICalculator:
    """
    Return on Investment calculations with confidence intervals.
    """

    @staticmethod
    def calculate_roi(bets: List[PredictionOutcome]) -> float:
        """
        ROI = (total_pnl / total_staked)

        Args:
            bets: List of settled bets with stake and pnl

        Returns:
            ROI as decimal (0.05 = 5% ROI)
        """
        total_staked = sum(b.stake for b in bets if b.stake > 0)
        total_pnl = sum(b.pnl for b in bets)

        if total_staked == 0:
            return float('nan')
        return total_pnl / total_staked

    @staticmethod
    def sharpe_ratio(bets: List[PredictionOutcome], risk_free_rate: float = 0.0) -> float:
        """
        Sharpe Ratio = (mean_return - risk_free_rate) / std_return

        Risk-adjusted return metric.
        - > 1.0 is considered good
        - > 2.0 is very good
        - > 3.0 is excellent

        Args:
            bets: List of settled bets with stake and pnl
            risk_free_rate: Risk-free rate (default 0)

        Returns:
            Sharpe ratio (float)
        """
        returns = []
        for bet in bets:
            if bet.stake > 0:
                returns.append(bet.pnl / bet.stake)

        if len(returns) < 2:
            return float('nan')

        mean_return = sum(returns) / len(returns)
        variance = sum((r - mean_return) ** 2 for r in returns) / (len(returns) - 1)
        std_return = math.sqrt(variance)

        if std_return == 0:
            return float('nan')

        return (mean_return - risk_free_rate) / std_return

    @staticmethod
    def roi_confidence_interval(
        bets: List[PredictionOutcome],
        confidence: float = 0.95,
        n_bootstrap: int = 1000
    ) -> Dict:
        """
        Calculate ROI with confidence interval using bootstrap.

        Args:
            bets: List of settled bets
            confidence: Confidence level (default 0.95)
            n_bootstrap: Number of bootstrap samples

        Returns:
            Dict with mean, lower, upper bounds
        """
        import random

        if len(bets) < 10:
            return {
                'mean': ROICalculator.calculate_roi(bets),
                'lower': float('nan'),
                'upper': float('nan'),
                'confidence': confidence
            }

        roi_samples = []
        for _ in range(n_bootstrap):
            sample = random.choices(bets, k=len(bets))
            roi = ROICalculator.calculate_roi(sample)
            if not math.isnan(roi):
                roi_samples.append(roi)

        if not roi_samples:
            return {
                'mean': float('nan'),
                'lower': float('nan'),
                'upper': float('nan'),
                'confidence': confidence
            }

        roi_samples.sort()
        lower_idx = int((1 - confidence) / 2 * len(roi_samples))
        upper_idx = int((1 + confidence) / 2 * len(roi_samples))

        return {
            'mean': sum(roi_samples) / len(roi_samples),
            'lower': roi_samples[lower_idx],
            'upper': roi_samples[min(upper_idx, len(roi_samples) - 1)],
            'confidence': confidence
        }


class ValidationReport:
    """
    Generates comprehensive validation report for Phase 0 exit criteria.

    Exit criteria:
    - clv_mean: > 0
    - roi_95ci_lower: > 0
    - brier_score: < 0.25
    - min_decisions: 500
    """

    def __init__(self, bets: List[PredictionOutcome]):
        self.bets = bets
        self.predictions = [b.p_model for b in bets]
        self.outcomes = [b.outcome for b in bets]

    def generate(self) -> Dict:
        """Generate full validation report."""
        cal = CalibrationMetrics()
        clv = CLVCalculator()
        roi = ROICalculator()

        roi_ci = roi.roi_confidence_interval(self.bets)
        clv_breakdown = clv.clv_breakdown(self.bets)

        report = {
            # Calibration
            'brier_score': cal.brier_score(self.predictions, self.outcomes),
            'log_loss': cal.log_loss(self.predictions, self.outcomes),
            'ece': cal.expected_calibration_error(self.predictions, self.outcomes),
            'calibration_bins': cal.calibration_bins(self.predictions, self.outcomes),

            # CLV
            'clv_mean': clv_breakdown['mean'],
            'clv_median': clv_breakdown['median'],
            'clv_positive_pct': clv_breakdown['positive_pct'],
            'clv_std': clv_breakdown['std'],

            # ROI
            'roi': roi.calculate_roi(self.bets),
            'roi_95ci_lower': roi_ci['lower'],
            'roi_95ci_upper': roi_ci['upper'],
            'sharpe_ratio': roi.sharpe_ratio(self.bets),

            # Volume
            'total_bets': len(self.bets),
            'total_staked': sum(b.stake for b in self.bets),
            'total_pnl': sum(b.pnl for b in self.bets),

            # Exit criteria check
            'exit_criteria': self._check_exit_criteria(
                clv_breakdown['mean'],
                roi_ci['lower'],
                cal.brier_score(self.predictions, self.outcomes),
                len(self.bets)
            )
        }

        return report

    def _check_exit_criteria(
        self,
        clv_mean: float,
        roi_lower: float,
        brier: float,
        n_bets: int
    ) -> Dict:
        """Check Phase 0 exit criteria."""
        return {
            'clv_positive': not math.isnan(clv_mean) and clv_mean > 0,
            'roi_ci_positive': not math.isnan(roi_lower) and roi_lower > 0,
            'brier_acceptable': not math.isnan(brier) and brier < 0.25,
            'min_decisions_met': n_bets >= 500,
            'all_passed': (
                (not math.isnan(clv_mean) and clv_mean > 0) and
                (not math.isnan(roi_lower) and roi_lower > 0) and
                (not math.isnan(brier) and brier < 0.25) and
                n_bets >= 500
            )
        }
