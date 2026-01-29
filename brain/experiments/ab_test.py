"""
A/B Testing Framework - Phase 3

Run parallel strategies to validate improvements.

Features:
- Traffic splitting (control vs treatment)
- Statistical significance testing
- Automatic promotion/rejection
- Experiment lifecycle management
"""

import math
import random
import statistics
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple


class ExperimentStatus(Enum):
    """Experiment lifecycle status."""
    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    PROMOTED = "promoted"
    REJECTED = "rejected"


class Variant(Enum):
    """Experiment variants."""
    CONTROL = "control"
    TREATMENT = "treatment"


@dataclass
class VariantMetrics:
    """Metrics for a single variant."""
    variant: Variant
    samples: int = 0
    bets: int = 0
    wins: int = 0
    total_pnl: float = 0.0
    total_staked: float = 0.0
    pnl_list: List[float] = field(default_factory=list)

    @property
    def win_rate(self) -> float:
        return self.wins / self.bets if self.bets > 0 else 0.0

    @property
    def roi(self) -> float:
        return self.total_pnl / self.total_staked if self.total_staked > 0 else 0.0

    @property
    def mean_pnl(self) -> float:
        return statistics.mean(self.pnl_list) if self.pnl_list else 0.0

    @property
    def std_pnl(self) -> float:
        return statistics.stdev(self.pnl_list) if len(self.pnl_list) > 1 else 0.0

    def to_dict(self) -> Dict:
        return {
            "variant": self.variant.value,
            "samples": self.samples,
            "bets": self.bets,
            "wins": self.wins,
            "win_rate": f"{self.win_rate:.1%}",
            "roi": f"{self.roi:+.2%}",
            "total_pnl": round(self.total_pnl, 2),
            "mean_pnl": round(self.mean_pnl, 4),
            "std_pnl": round(self.std_pnl, 4),
        }


@dataclass
class ExperimentResult:
    """Result of experiment evaluation."""
    decision: str  # PROMOTE, KEEP_CONTROL, INSUFFICIENT_DATA
    p_value: float
    effect_size: float
    confidence: float
    control_metrics: VariantMetrics
    treatment_metrics: VariantMetrics
    recommendation: str

    def to_dict(self) -> Dict:
        return {
            "decision": self.decision,
            "p_value": round(self.p_value, 4),
            "effect_size": f"{self.effect_size:+.2%}",
            "confidence": f"{self.confidence:.1%}",
            "control": self.control_metrics.to_dict(),
            "treatment": self.treatment_metrics.to_dict(),
            "recommendation": self.recommendation,
        }


@dataclass
class Experiment:
    """
    A/B Test experiment definition.

    Tracks control vs treatment performance.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    description: str = ""

    # Configuration
    treatment_changes: Dict = field(default_factory=dict)
    allocation: float = 0.2  # % of traffic to treatment

    # State
    status: ExperimentStatus = ExperimentStatus.DRAFT
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None

    # Metrics
    control: VariantMetrics = field(
        default_factory=lambda: VariantMetrics(Variant.CONTROL)
    )
    treatment: VariantMetrics = field(
        default_factory=lambda: VariantMetrics(Variant.TREATMENT)
    )

    # Thresholds
    min_samples: int = 100
    min_duration_hours: int = 48
    significance_level: float = 0.05  # p < 0.05

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "allocation": f"{self.allocation:.0%}",
            "changes": self.treatment_changes,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "control": self.control.to_dict(),
            "treatment": self.treatment.to_dict(),
            "min_samples": self.min_samples,
        }


class ABTest:
    """
    A/B Testing manager.

    Usage:
        ab = ABTest()

        # Create experiment
        exp = ab.create_experiment(
            name="higher_ev_threshold",
            changes={"EV_MIN": 0.07},
            allocation=0.2,
        )

        # During runtime, get variant and params
        variant, params = ab.get_variant(exp.id, base_params)

        # Record outcomes
        ab.record_outcome(exp.id, variant, won=True, pnl=1.5, stake=10)

        # Evaluate when ready
        result = ab.evaluate(exp.id)
        if result.decision == "PROMOTE":
            ab.promote(exp.id)
    """

    def __init__(self):
        self.experiments: Dict[str, Experiment] = {}

    def create_experiment(
        self,
        name: str,
        changes: Dict,
        allocation: float = 0.2,
        description: str = "",
        min_samples: int = 100,
    ) -> Experiment:
        """
        Create a new experiment.

        Args:
            name: Experiment name
            changes: Dict of parameter changes for treatment
            allocation: Fraction of traffic to treatment (0-1)
            description: Optional description
            min_samples: Minimum samples before evaluation

        Returns:
            Created Experiment
        """
        exp = Experiment(
            name=name,
            description=description,
            treatment_changes=changes,
            allocation=allocation,
            min_samples=min_samples,
        )

        self.experiments[exp.id] = exp
        return exp

    def start_experiment(self, experiment_id: str) -> bool:
        """Start an experiment."""
        if experiment_id not in self.experiments:
            return False

        exp = self.experiments[experiment_id]
        if exp.status != ExperimentStatus.DRAFT:
            return False

        exp.status = ExperimentStatus.RUNNING
        exp.started_at = datetime.utcnow()
        return True

    def pause_experiment(self, experiment_id: str) -> bool:
        """Pause a running experiment."""
        if experiment_id not in self.experiments:
            return False

        exp = self.experiments[experiment_id]
        if exp.status == ExperimentStatus.RUNNING:
            exp.status = ExperimentStatus.PAUSED
            return True
        return False

    def get_variant(
        self,
        experiment_id: str,
        base_params: Dict,
    ) -> Tuple[Variant, Dict]:
        """
        Get variant assignment and parameters for a decision.

        Args:
            experiment_id: Experiment ID
            base_params: Base parameter dict

        Returns:
            (variant, params) tuple
        """
        if experiment_id not in self.experiments:
            return Variant.CONTROL, base_params

        exp = self.experiments[experiment_id]
        if exp.status != ExperimentStatus.RUNNING:
            return Variant.CONTROL, base_params

        # Random assignment based on allocation
        if random.random() < exp.allocation:
            # Treatment: apply changes
            params = base_params.copy()
            params.update(exp.treatment_changes)
            exp.treatment.samples += 1
            return Variant.TREATMENT, params
        else:
            # Control: use base params
            exp.control.samples += 1
            return Variant.CONTROL, base_params

    def record_outcome(
        self,
        experiment_id: str,
        variant: Variant,
        won: bool,
        pnl: float,
        stake: float = 10.0,
    ) -> None:
        """
        Record bet outcome for experiment.

        Args:
            experiment_id: Experiment ID
            variant: Which variant was used
            won: Whether bet won
            pnl: Profit/loss amount
            stake: Stake amount
        """
        if experiment_id not in self.experiments:
            return

        exp = self.experiments[experiment_id]
        metrics = exp.treatment if variant == Variant.TREATMENT else exp.control

        metrics.bets += 1
        if won:
            metrics.wins += 1
        metrics.total_pnl += pnl
        metrics.total_staked += stake
        metrics.pnl_list.append(pnl)

    def evaluate(
        self,
        experiment_id: str,
        metric: str = "roi",
    ) -> ExperimentResult:
        """
        Evaluate experiment results.

        Args:
            experiment_id: Experiment ID
            metric: Metric to compare ("roi", "win_rate", "pnl")

        Returns:
            ExperimentResult with decision
        """
        if experiment_id not in self.experiments:
            return self._insufficient_data_result()

        exp = self.experiments[experiment_id]

        # Check minimum samples
        total_samples = exp.control.bets + exp.treatment.bets
        if total_samples < exp.min_samples:
            return ExperimentResult(
                decision="INSUFFICIENT_DATA",
                p_value=1.0,
                effect_size=0.0,
                confidence=0.0,
                control_metrics=exp.control,
                treatment_metrics=exp.treatment,
                recommendation=f"Need {exp.min_samples - total_samples} more samples",
            )

        # Check minimum duration
        if exp.started_at:
            hours_running = (datetime.utcnow() - exp.started_at).total_seconds() / 3600
            if hours_running < exp.min_duration_hours:
                return ExperimentResult(
                    decision="INSUFFICIENT_DATA",
                    p_value=1.0,
                    effect_size=0.0,
                    confidence=0.0,
                    control_metrics=exp.control,
                    treatment_metrics=exp.treatment,
                    recommendation=f"Need {exp.min_duration_hours - hours_running:.0f} more hours",
                )

        # Statistical test
        p_value, effect_size = self._t_test(
            exp.control.pnl_list,
            exp.treatment.pnl_list,
        )

        confidence = 1 - p_value

        # Decision
        if p_value < exp.significance_level:
            if effect_size > 0:
                decision = "PROMOTE"
                recommendation = f"Treatment is significantly better (+{effect_size:.1%} ROI). Recommend promotion."
            else:
                decision = "KEEP_CONTROL"
                recommendation = f"Treatment is significantly worse ({effect_size:.1%} ROI). Keep control."
        else:
            decision = "KEEP_CONTROL"
            recommendation = f"No significant difference (p={p_value:.3f}). Keep control."

        return ExperimentResult(
            decision=decision,
            p_value=p_value,
            effect_size=effect_size,
            confidence=confidence,
            control_metrics=exp.control,
            treatment_metrics=exp.treatment,
            recommendation=recommendation,
        )

    def promote(self, experiment_id: str) -> Dict:
        """
        Promote treatment to become new control.

        Returns:
            Dict with the changes to apply
        """
        if experiment_id not in self.experiments:
            return {}

        exp = self.experiments[experiment_id]
        exp.status = ExperimentStatus.PROMOTED
        exp.ended_at = datetime.utcnow()

        return exp.treatment_changes.copy()

    def reject(self, experiment_id: str) -> None:
        """Reject experiment and keep control."""
        if experiment_id in self.experiments:
            exp = self.experiments[experiment_id]
            exp.status = ExperimentStatus.REJECTED
            exp.ended_at = datetime.utcnow()

    def get_active_experiments(self) -> List[Experiment]:
        """Get all running experiments."""
        return [
            exp for exp in self.experiments.values()
            if exp.status == ExperimentStatus.RUNNING
        ]

    def get_experiment(self, experiment_id: str) -> Optional[Experiment]:
        """Get experiment by ID."""
        return self.experiments.get(experiment_id)

    def _t_test(
        self,
        control: List[float],
        treatment: List[float],
    ) -> Tuple[float, float]:
        """
        Welch's t-test for unequal variances.

        Returns:
            (p_value, effect_size) tuple
        """
        if len(control) < 2 or len(treatment) < 2:
            return 1.0, 0.0

        # Means
        mean_c = statistics.mean(control)
        mean_t = statistics.mean(treatment)

        # Variances
        var_c = statistics.variance(control)
        var_t = statistics.variance(treatment)

        n_c = len(control)
        n_t = len(treatment)

        # Standard error
        se = math.sqrt(var_c / n_c + var_t / n_t)
        if se == 0:
            return 1.0, 0.0

        # T statistic
        t_stat = (mean_t - mean_c) / se

        # Degrees of freedom (Welch-Satterthwaite)
        num = (var_c / n_c + var_t / n_t) ** 2
        denom = (var_c / n_c) ** 2 / (n_c - 1) + (var_t / n_t) ** 2 / (n_t - 1)
        df = num / denom if denom > 0 else 1

        # P-value (two-tailed, approximate using normal for large df)
        # Using normal approximation for simplicity
        p_value = 2 * (1 - self._normal_cdf(abs(t_stat)))

        # Effect size (difference in means relative to pooled std)
        pooled_std = math.sqrt((var_c + var_t) / 2)
        effect_size = (mean_t - mean_c) / pooled_std if pooled_std > 0 else 0.0

        return p_value, effect_size

    def _normal_cdf(self, x: float) -> float:
        """Approximate normal CDF."""
        return 0.5 * (1 + math.erf(x / math.sqrt(2)))

    def _insufficient_data_result(self) -> ExperimentResult:
        """Return result for insufficient data."""
        empty = VariantMetrics(Variant.CONTROL)
        return ExperimentResult(
            decision="INSUFFICIENT_DATA",
            p_value=1.0,
            effect_size=0.0,
            confidence=0.0,
            control_metrics=empty,
            treatment_metrics=empty,
            recommendation="Experiment not found",
        )


# Convenience function
def run_ab_test(
    control_results: List[float],
    treatment_results: List[float],
    significance: float = 0.05,
) -> Dict:
    """
    Quick A/B test evaluation.

    Args:
        control_results: List of PnL values for control
        treatment_results: List of PnL values for treatment
        significance: P-value threshold

    Returns:
        Dict with test results
    """
    ab = ABTest()

    exp = ab.create_experiment(
        name="quick_test",
        changes={},
        min_samples=1,
    )
    ab.start_experiment(exp.id)

    # Add results
    exp.control.pnl_list = control_results
    exp.control.bets = len(control_results)
    exp.treatment.pnl_list = treatment_results
    exp.treatment.bets = len(treatment_results)

    exp.significance_level = significance
    exp.min_duration_hours = 0

    result = ab.evaluate(exp.id)
    return result.to_dict()
