"""
Graduation Checker - Phase 4

Validates readiness for live trading based on paper performance.

Criteria:
- Minimum paper bets (500+)
- Positive ROI (3%+)
- Positive CLV (1%+)
- Maximum drawdown (< 15%)
- Fill rate simulation (70%+)
- System uptime (99%+)
- Signal accuracy (60%+)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional


class CriterionStatus(Enum):
    """Status of a graduation criterion."""
    PASSED = "passed"
    FAILED = "failed"
    PENDING = "pending"  # Not enough data


@dataclass
class CriterionResult:
    """Result of evaluating a single criterion."""
    name: str
    status: CriterionStatus
    required: float
    actual: float
    margin: float  # How much above/below threshold
    message: str

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "status": self.status.value,
            "required": self.required,
            "actual": round(self.actual, 4),
            "margin": f"{self.margin:+.2%}",
            "message": self.message,
        }


@dataclass
class GraduationResult:
    """Complete graduation evaluation result."""
    passed: bool
    criteria: List[CriterionResult]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    summary: str = ""

    @property
    def passed_count(self) -> int:
        return len([c for c in self.criteria if c.status == CriterionStatus.PASSED])

    @property
    def failed_count(self) -> int:
        return len([c for c in self.criteria if c.status == CriterionStatus.FAILED])

    @property
    def pending_count(self) -> int:
        return len([c for c in self.criteria if c.status == CriterionStatus.PENDING])

    def to_dict(self) -> Dict:
        return {
            "passed": self.passed,
            "summary": self.summary,
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "pending_count": self.pending_count,
            "criteria": [c.to_dict() for c in self.criteria],
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class GraduationCriteria:
    """Configurable graduation criteria."""
    min_paper_bets: int = 500
    min_paper_roi: float = 0.03       # 3%
    min_paper_clv: float = 0.01       # 1%
    max_drawdown: float = 0.15        # 15%
    min_fill_rate: float = 0.70       # 70%
    min_uptime: float = 0.99          # 99%
    min_signal_accuracy: float = 0.60  # 60%
    min_sharpe_ratio: float = 0.5     # Risk-adjusted

    def to_dict(self) -> Dict:
        return {
            "min_paper_bets": self.min_paper_bets,
            "min_paper_roi": f"{self.min_paper_roi:.1%}",
            "min_paper_clv": f"{self.min_paper_clv:.1%}",
            "max_drawdown": f"{self.max_drawdown:.1%}",
            "min_fill_rate": f"{self.min_fill_rate:.1%}",
            "min_uptime": f"{self.min_uptime:.1%}",
            "min_signal_accuracy": f"{self.min_signal_accuracy:.1%}",
            "min_sharpe_ratio": self.min_sharpe_ratio,
        }


@dataclass
class PaperPerformance:
    """Paper trading performance metrics."""
    total_bets: int = 0
    wins: int = 0
    total_staked: float = 0.0
    total_pnl: float = 0.0
    peak_bankroll: float = 1000.0
    min_bankroll: float = 1000.0
    current_bankroll: float = 1000.0

    clv_sum: float = 0.0
    filled_count: int = 0
    signal_correct: int = 0  # For HARD signals

    uptime_seconds: float = 0.0
    total_seconds: float = 86400.0  # Default 1 day

    pnl_list: List[float] = field(default_factory=list)

    @property
    def roi(self) -> float:
        return self.total_pnl / self.total_staked if self.total_staked > 0 else 0.0

    @property
    def win_rate(self) -> float:
        return self.wins / self.total_bets if self.total_bets > 0 else 0.0

    @property
    def avg_clv(self) -> float:
        return self.clv_sum / self.total_bets if self.total_bets > 0 else 0.0

    @property
    def max_drawdown(self) -> float:
        if self.peak_bankroll <= 0:
            return 0.0
        return (self.peak_bankroll - self.min_bankroll) / self.peak_bankroll

    @property
    def fill_rate(self) -> float:
        return self.filled_count / self.total_bets if self.total_bets > 0 else 0.0

    @property
    def uptime(self) -> float:
        return self.uptime_seconds / self.total_seconds if self.total_seconds > 0 else 0.0

    @property
    def signal_accuracy(self) -> float:
        return self.signal_correct / self.total_bets if self.total_bets > 0 else 0.0

    @property
    def sharpe_ratio(self) -> float:
        if len(self.pnl_list) < 2:
            return 0.0
        import statistics
        mean_pnl = statistics.mean(self.pnl_list)
        std_pnl = statistics.stdev(self.pnl_list)
        if std_pnl == 0:
            return 0.0
        return mean_pnl / std_pnl


class GraduationChecker:
    """
    Check if paper trading performance meets graduation criteria.

    Usage:
        checker = GraduationChecker()

        performance = PaperPerformance(
            total_bets=600,
            wins=330,
            total_pnl=150,
            total_staked=3000,
            ...
        )

        result = checker.evaluate(performance)
        if result.passed:
            print("Ready for live trading!")
        else:
            print(f"Not ready: {result.summary}")
    """

    def __init__(self, criteria: Optional[GraduationCriteria] = None):
        self.criteria = criteria or GraduationCriteria()
        self.logger = logging.getLogger("graduation_checker")

    def evaluate(self, performance: PaperPerformance) -> GraduationResult:
        """
        Evaluate paper performance against graduation criteria.

        Args:
            performance: Paper trading performance metrics

        Returns:
            GraduationResult with detailed breakdown
        """
        results = []

        # 1. Minimum bets
        results.append(self._check_min_bets(performance))

        # 2. ROI
        results.append(self._check_roi(performance))

        # 3. CLV
        results.append(self._check_clv(performance))

        # 4. Drawdown
        results.append(self._check_drawdown(performance))

        # 5. Fill rate
        results.append(self._check_fill_rate(performance))

        # 6. Uptime
        results.append(self._check_uptime(performance))

        # 7. Signal accuracy
        results.append(self._check_signal_accuracy(performance))

        # 8. Sharpe ratio
        results.append(self._check_sharpe(performance))

        # Overall result
        all_passed = all(r.status == CriterionStatus.PASSED for r in results)
        any_failed = any(r.status == CriterionStatus.FAILED for r in results)

        if all_passed:
            passed = True
            summary = "All graduation criteria met. Ready for live trading."
        elif any_failed:
            passed = False
            failed = [r.name for r in results if r.status == CriterionStatus.FAILED]
            summary = f"Failed criteria: {', '.join(failed)}"
        else:
            passed = False
            pending = [r.name for r in results if r.status == CriterionStatus.PENDING]
            summary = f"Insufficient data for: {', '.join(pending)}"

        result = GraduationResult(
            passed=passed,
            criteria=results,
            summary=summary,
        )

        self.logger.info(f"Graduation check: {'PASSED' if passed else 'FAILED'} - {summary}")

        return result

    def _check_min_bets(self, perf: PaperPerformance) -> CriterionResult:
        """Check minimum bet count."""
        required = self.criteria.min_paper_bets
        actual = perf.total_bets

        if actual >= required:
            status = CriterionStatus.PASSED
            message = f"Sufficient bets: {actual} >= {required}"
        else:
            status = CriterionStatus.PENDING
            message = f"Need {required - actual} more bets"

        return CriterionResult(
            name="min_bets",
            status=status,
            required=required,
            actual=actual,
            margin=(actual - required) / required if required > 0 else 0,
            message=message,
        )

    def _check_roi(self, perf: PaperPerformance) -> CriterionResult:
        """Check ROI threshold."""
        required = self.criteria.min_paper_roi
        actual = perf.roi

        if perf.total_bets < 100:
            status = CriterionStatus.PENDING
            message = "Not enough bets for reliable ROI"
        elif actual >= required:
            status = CriterionStatus.PASSED
            message = f"ROI {actual:.2%} >= {required:.2%}"
        else:
            status = CriterionStatus.FAILED
            message = f"ROI {actual:.2%} < {required:.2%}"

        return CriterionResult(
            name="roi",
            status=status,
            required=required,
            actual=actual,
            margin=actual - required,
            message=message,
        )

    def _check_clv(self, perf: PaperPerformance) -> CriterionResult:
        """Check CLV threshold."""
        required = self.criteria.min_paper_clv
        actual = perf.avg_clv

        if perf.total_bets < 100:
            status = CriterionStatus.PENDING
            message = "Not enough bets for reliable CLV"
        elif actual >= required:
            status = CriterionStatus.PASSED
            message = f"CLV {actual:.2%} >= {required:.2%}"
        else:
            status = CriterionStatus.FAILED
            message = f"CLV {actual:.2%} < {required:.2%}"

        return CriterionResult(
            name="clv",
            status=status,
            required=required,
            actual=actual,
            margin=actual - required,
            message=message,
        )

    def _check_drawdown(self, perf: PaperPerformance) -> CriterionResult:
        """Check maximum drawdown."""
        max_allowed = self.criteria.max_drawdown
        actual = perf.max_drawdown

        if perf.total_bets < 50:
            status = CriterionStatus.PENDING
            message = "Not enough data for drawdown analysis"
        elif actual <= max_allowed:
            status = CriterionStatus.PASSED
            message = f"Drawdown {actual:.1%} <= {max_allowed:.1%}"
        else:
            status = CriterionStatus.FAILED
            message = f"Drawdown {actual:.1%} > {max_allowed:.1%}"

        return CriterionResult(
            name="max_drawdown",
            status=status,
            required=max_allowed,
            actual=actual,
            margin=max_allowed - actual,
            message=message,
        )

    def _check_fill_rate(self, perf: PaperPerformance) -> CriterionResult:
        """Check simulated fill rate."""
        required = self.criteria.min_fill_rate
        actual = perf.fill_rate

        if perf.total_bets < 50:
            status = CriterionStatus.PENDING
            message = "Not enough data for fill rate"
        elif actual >= required:
            status = CriterionStatus.PASSED
            message = f"Fill rate {actual:.1%} >= {required:.1%}"
        else:
            status = CriterionStatus.FAILED
            message = f"Fill rate {actual:.1%} < {required:.1%}"

        return CriterionResult(
            name="fill_rate",
            status=status,
            required=required,
            actual=actual,
            margin=actual - required,
            message=message,
        )

    def _check_uptime(self, perf: PaperPerformance) -> CriterionResult:
        """Check system uptime."""
        required = self.criteria.min_uptime
        actual = perf.uptime

        if perf.total_seconds < 86400:  # Less than 1 day
            status = CriterionStatus.PENDING
            message = "Not enough runtime for uptime check"
        elif actual >= required:
            status = CriterionStatus.PASSED
            message = f"Uptime {actual:.2%} >= {required:.2%}"
        else:
            status = CriterionStatus.FAILED
            message = f"Uptime {actual:.2%} < {required:.2%}"

        return CriterionResult(
            name="uptime",
            status=status,
            required=required,
            actual=actual,
            margin=actual - required,
            message=message,
        )

    def _check_signal_accuracy(self, perf: PaperPerformance) -> CriterionResult:
        """Check signal accuracy."""
        required = self.criteria.min_signal_accuracy
        actual = perf.signal_accuracy

        if perf.total_bets < 100:
            status = CriterionStatus.PENDING
            message = "Not enough data for signal accuracy"
        elif actual >= required:
            status = CriterionStatus.PASSED
            message = f"Signal accuracy {actual:.1%} >= {required:.1%}"
        else:
            status = CriterionStatus.FAILED
            message = f"Signal accuracy {actual:.1%} < {required:.1%}"

        return CriterionResult(
            name="signal_accuracy",
            status=status,
            required=required,
            actual=actual,
            margin=actual - required,
            message=message,
        )

    def _check_sharpe(self, perf: PaperPerformance) -> CriterionResult:
        """Check Sharpe ratio."""
        required = self.criteria.min_sharpe_ratio
        actual = perf.sharpe_ratio

        if len(perf.pnl_list) < 30:
            status = CriterionStatus.PENDING
            message = "Not enough data for Sharpe calculation"
        elif actual >= required:
            status = CriterionStatus.PASSED
            message = f"Sharpe {actual:.2f} >= {required:.2f}"
        else:
            status = CriterionStatus.FAILED
            message = f"Sharpe {actual:.2f} < {required:.2f}"

        return CriterionResult(
            name="sharpe_ratio",
            status=status,
            required=required,
            actual=actual,
            margin=(actual - required) / required if required > 0 else 0,
            message=message,
        )

    def get_criteria(self) -> Dict:
        """Get current graduation criteria."""
        return self.criteria.to_dict()

    def update_criterion(self, name: str, value: float) -> bool:
        """Update a specific criterion threshold."""
        if hasattr(self.criteria, name):
            setattr(self.criteria, name, value)
            self.logger.info(f"Updated criterion {name} to {value}")
            return True
        return False


# Convenience function
def check_graduation(
    total_bets: int,
    wins: int,
    total_pnl: float,
    total_staked: float,
    clv_avg: float,
    max_drawdown: float,
    fill_rate: float = 0.8,
) -> Dict:
    """
    Quick graduation check.

    Returns:
        Dict with passed status and summary
    """
    perf = PaperPerformance(
        total_bets=total_bets,
        wins=wins,
        total_pnl=total_pnl,
        total_staked=total_staked,
        clv_sum=clv_avg * total_bets,
        filled_count=int(fill_rate * total_bets),
        signal_correct=wins,
        uptime_seconds=86400 * 30,  # 30 days
        total_seconds=86400 * 30,
    )

    # Set peak/min for drawdown
    perf.peak_bankroll = 1000 + total_pnl * 1.2
    perf.min_bankroll = perf.peak_bankroll * (1 - max_drawdown)

    checker = GraduationChecker()
    result = checker.evaluate(perf)

    return result.to_dict()
