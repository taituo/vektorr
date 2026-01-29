"""
Staged Rollout - Phase 4

Manages progressive transition from paper to live trading.

Stages:
1. SHADOW: Live data, paper decisions, compare to simulation
2. MICRO: €1-5 stakes, max €50/day exposure
3. SMALL: €10-25 stakes, max €200/day exposure
4. TARGET: Kelly-optimized sizing, full operation
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, Dict, List, Optional


class Stage(Enum):
    """Rollout stages."""
    PAPER = "paper"       # Pure simulation
    SHADOW = "shadow"     # Live data, paper decisions
    MICRO = "micro"       # €1-5 stakes
    SMALL = "small"       # €10-25 stakes
    TARGET = "target"     # Full Kelly sizing


@dataclass
class StageConfig:
    """Configuration for a rollout stage."""
    stage: Stage
    min_stake: float
    max_stake: float
    max_daily_exposure: float
    max_bets_per_day: int
    min_duration_days: int
    description: str

    def to_dict(self) -> Dict:
        return {
            "stage": self.stage.value,
            "min_stake": self.min_stake,
            "max_stake": self.max_stake,
            "max_daily_exposure": self.max_daily_exposure,
            "max_bets_per_day": self.max_bets_per_day,
            "min_duration_days": self.min_duration_days,
            "description": self.description,
        }


# Default stage configurations
DEFAULT_STAGE_CONFIGS = {
    Stage.PAPER: StageConfig(
        stage=Stage.PAPER,
        min_stake=0,
        max_stake=0,
        max_daily_exposure=0,
        max_bets_per_day=999,
        min_duration_days=14,
        description="Pure paper trading simulation",
    ),
    Stage.SHADOW: StageConfig(
        stage=Stage.SHADOW,
        min_stake=0,
        max_stake=0,
        max_daily_exposure=0,
        max_bets_per_day=999,
        min_duration_days=14,
        description="Live data, paper decisions, compare to simulation",
    ),
    Stage.MICRO: StageConfig(
        stage=Stage.MICRO,
        min_stake=1,
        max_stake=5,
        max_daily_exposure=50,
        max_bets_per_day=20,
        min_duration_days=28,
        description="Micro stakes: €1-5, max €50/day",
    ),
    Stage.SMALL: StageConfig(
        stage=Stage.SMALL,
        min_stake=10,
        max_stake=25,
        max_daily_exposure=200,
        max_bets_per_day=15,
        min_duration_days=28,
        description="Small stakes: €10-25, max €200/day",
    ),
    Stage.TARGET: StageConfig(
        stage=Stage.TARGET,
        min_stake=10,
        max_stake=100,
        max_daily_exposure=500,
        max_bets_per_day=20,
        min_duration_days=0,  # No minimum
        description="Target stakes: Kelly-optimized",
    ),
}


@dataclass
class StageMetrics:
    """Metrics tracked during a stage."""
    bets: int = 0
    wins: int = 0
    total_staked: float = 0.0
    total_pnl: float = 0.0
    fill_rate: float = 0.0
    clv_sum: float = 0.0

    started_at: Optional[datetime] = None
    daily_exposure: float = 0.0
    daily_bets: int = 0
    last_reset_date: Optional[datetime] = None

    @property
    def roi(self) -> float:
        return self.total_pnl / self.total_staked if self.total_staked > 0 else 0.0

    @property
    def win_rate(self) -> float:
        return self.wins / self.bets if self.bets > 0 else 0.0

    @property
    def avg_clv(self) -> float:
        return self.clv_sum / self.bets if self.bets > 0 else 0.0

    @property
    def days_in_stage(self) -> int:
        if not self.started_at:
            return 0
        return (datetime.utcnow() - self.started_at).days

    def to_dict(self) -> Dict:
        return {
            "bets": self.bets,
            "wins": self.wins,
            "win_rate": f"{self.win_rate:.1%}",
            "roi": f"{self.roi:+.2%}",
            "total_pnl": round(self.total_pnl, 2),
            "avg_clv": f"{self.avg_clv:+.2%}",
            "days_in_stage": self.days_in_stage,
        }


class StagedRollout:
    """
    Manages staged rollout from paper to live.

    Usage:
        rollout = StagedRollout(initial_stage=Stage.SHADOW)

        # Get current stake limits
        config = rollout.get_current_config()
        stake = rollout.calculate_stake(kelly_stake=15, ev=0.05)

        # Record outcomes
        rollout.record_bet(stake=5, pnl=7.5, won=True, filled=True, clv=0.02)

        # Check if ready for next stage
        if rollout.can_advance():
            rollout.advance_stage(approver="admin")
    """

    def __init__(
        self,
        initial_stage: Stage = Stage.PAPER,
        configs: Optional[Dict[Stage, StageConfig]] = None,
        on_stage_change: Optional[Callable[[Stage, Stage], None]] = None,
    ):
        self.configs = configs or DEFAULT_STAGE_CONFIGS.copy()
        self.on_stage_change = on_stage_change

        self.current_stage = initial_stage
        self.stage_history: List[Dict] = []

        # Metrics per stage
        self.metrics: Dict[Stage, StageMetrics] = {
            stage: StageMetrics() for stage in Stage
        }
        self.metrics[initial_stage].started_at = datetime.utcnow()

        self.logger = logging.getLogger("staged_rollout")

    def get_current_config(self) -> StageConfig:
        """Get configuration for current stage."""
        return self.configs[self.current_stage]

    def get_current_metrics(self) -> StageMetrics:
        """Get metrics for current stage."""
        return self.metrics[self.current_stage]

    def calculate_stake(
        self,
        kelly_stake: float,
        ev: float,
        confidence: float = 1.0,
    ) -> float:
        """
        Calculate stake respecting current stage limits.

        Args:
            kelly_stake: Kelly criterion suggested stake
            ev: Expected value of bet
            confidence: Model confidence (0-1)

        Returns:
            Allowed stake amount
        """
        config = self.get_current_config()
        metrics = self.get_current_metrics()

        # Paper/shadow stages don't place real bets
        if config.stage in (Stage.PAPER, Stage.SHADOW):
            return 0.0

        # Check daily limits
        self._check_daily_reset()

        remaining_exposure = config.max_daily_exposure - metrics.daily_exposure
        if remaining_exposure <= 0:
            self.logger.warning("Daily exposure limit reached")
            return 0.0

        if metrics.daily_bets >= config.max_bets_per_day:
            self.logger.warning("Daily bet limit reached")
            return 0.0

        # Apply stage limits
        stake = min(
            kelly_stake * confidence,
            config.max_stake,
            remaining_exposure,
        )
        stake = max(stake, config.min_stake)

        return round(stake, 2)

    def record_bet(
        self,
        stake: float,
        pnl: float,
        won: bool,
        filled: bool = True,
        clv: float = 0.0,
    ) -> None:
        """
        Record a bet outcome.

        Args:
            stake: Amount staked
            pnl: Profit/loss
            won: Whether bet won
            filled: Whether bet was filled
            clv: Closing line value
        """
        metrics = self.get_current_metrics()
        self._check_daily_reset()

        metrics.bets += 1
        if won:
            metrics.wins += 1

        metrics.total_staked += stake
        metrics.total_pnl += pnl
        metrics.clv_sum += clv

        # Daily tracking
        metrics.daily_exposure += stake
        metrics.daily_bets += 1

        # Fill rate (rolling average)
        if metrics.bets == 1:
            metrics.fill_rate = 1.0 if filled else 0.0
        else:
            # Exponential moving average
            alpha = 0.1
            metrics.fill_rate = alpha * (1.0 if filled else 0.0) + (1 - alpha) * metrics.fill_rate

    def _check_daily_reset(self) -> None:
        """Reset daily counters at day boundary."""
        metrics = self.get_current_metrics()
        today = datetime.utcnow().date()

        if metrics.last_reset_date != today:
            metrics.daily_exposure = 0.0
            metrics.daily_bets = 0
            metrics.last_reset_date = today

    def can_advance(self) -> tuple[bool, str]:
        """
        Check if ready to advance to next stage.

        Returns:
            (can_advance, reason)
        """
        config = self.get_current_config()
        metrics = self.get_current_metrics()

        # Already at target
        if self.current_stage == Stage.TARGET:
            return False, "Already at target stage"

        # Minimum duration
        if metrics.days_in_stage < config.min_duration_days:
            days_left = config.min_duration_days - metrics.days_in_stage
            return False, f"Need {days_left} more days in current stage"

        # Check advancement criteria based on stage
        if self.current_stage == Stage.PAPER:
            # Need positive ROI and CLV
            if metrics.bets < 100:
                return False, f"Need {100 - metrics.bets} more paper bets"
            if metrics.roi < 0:
                return False, f"Paper ROI is negative ({metrics.roi:.1%})"
            return True, "Ready to advance from PAPER"

        elif self.current_stage == Stage.SHADOW:
            # Shadow must match paper expectations
            if metrics.bets < 50:
                return False, f"Need {50 - metrics.bets} more shadow decisions"
            return True, "Ready to advance from SHADOW"

        elif self.current_stage == Stage.MICRO:
            if metrics.bets < 50:
                return False, f"Need {50 - metrics.bets} more micro bets"
            if metrics.roi < -0.10:
                return False, f"Micro ROI too negative ({metrics.roi:.1%})"
            if metrics.fill_rate < 0.60:
                return False, f"Fill rate too low ({metrics.fill_rate:.1%})"
            return True, "Ready to advance from MICRO"

        elif self.current_stage == Stage.SMALL:
            if metrics.bets < 100:
                return False, f"Need {100 - metrics.bets} more small bets"
            if metrics.roi < 0:
                return False, f"Small stakes ROI negative ({metrics.roi:.1%})"
            if metrics.fill_rate < 0.70:
                return False, f"Fill rate below 70% ({metrics.fill_rate:.1%})"
            return True, "Ready to advance to TARGET"

        return False, "Unknown stage"

    def advance_stage(self, approver: str = "system") -> bool:
        """
        Advance to next stage.

        Args:
            approver: Who approved the advancement

        Returns:
            True if successfully advanced
        """
        can_advance, reason = self.can_advance()
        if not can_advance:
            self.logger.warning(f"Cannot advance: {reason}")
            return False

        old_stage = self.current_stage
        stage_order = [Stage.PAPER, Stage.SHADOW, Stage.MICRO, Stage.SMALL, Stage.TARGET]
        current_idx = stage_order.index(self.current_stage)

        if current_idx >= len(stage_order) - 1:
            return False

        new_stage = stage_order[current_idx + 1]

        # Record transition
        self.stage_history.append({
            "from": old_stage.value,
            "to": new_stage.value,
            "timestamp": datetime.utcnow().isoformat(),
            "approver": approver,
            "metrics": self.get_current_metrics().to_dict(),
        })

        # Advance
        self.current_stage = new_stage
        self.metrics[new_stage].started_at = datetime.utcnow()

        self.logger.info(f"Advanced from {old_stage.value} to {new_stage.value} by {approver}")

        if self.on_stage_change:
            self.on_stage_change(old_stage, new_stage)

        return True

    def rollback_stage(self, reason: str = "") -> bool:
        """
        Rollback to previous stage (safety measure).

        Args:
            reason: Why rolling back

        Returns:
            True if successfully rolled back
        """
        stage_order = [Stage.PAPER, Stage.SHADOW, Stage.MICRO, Stage.SMALL, Stage.TARGET]
        current_idx = stage_order.index(self.current_stage)

        if current_idx <= 0:
            self.logger.warning("Cannot rollback from first stage")
            return False

        old_stage = self.current_stage
        new_stage = stage_order[current_idx - 1]

        self.stage_history.append({
            "from": old_stage.value,
            "to": new_stage.value,
            "timestamp": datetime.utcnow().isoformat(),
            "type": "rollback",
            "reason": reason,
        })

        self.current_stage = new_stage
        self.metrics[new_stage].started_at = datetime.utcnow()

        self.logger.warning(f"Rolled back from {old_stage.value} to {new_stage.value}: {reason}")

        if self.on_stage_change:
            self.on_stage_change(old_stage, new_stage)

        return True

    def get_status(self) -> Dict:
        """Get complete rollout status."""
        config = self.get_current_config()
        metrics = self.get_current_metrics()
        can_advance, advance_reason = self.can_advance()

        return {
            "current_stage": self.current_stage.value,
            "config": config.to_dict(),
            "metrics": metrics.to_dict(),
            "can_advance": can_advance,
            "advance_reason": advance_reason,
            "history": self.stage_history[-5:],
        }

    def is_live(self) -> bool:
        """Check if in live betting stages."""
        return self.current_stage in (Stage.MICRO, Stage.SMALL, Stage.TARGET)

    def is_paper(self) -> bool:
        """Check if in paper trading stages."""
        return self.current_stage in (Stage.PAPER, Stage.SHADOW)
