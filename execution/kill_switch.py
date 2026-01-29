"""
Kill Switch - Phase 4

Emergency stop system for live trading.

Monitors critical metrics and freezes system when thresholds breached.

Triggers:
- Daily loss limit
- Weekly loss limit
- Drawdown from peak
- Fill rate collapse
- Latency spike
- Error rate spike
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, Dict, List, Optional


class SystemState(Enum):
    """System operational state."""
    RUNNING = "running"
    FROZEN = "frozen"
    MANUAL_STOP = "manual_stop"
    MAINTENANCE = "maintenance"


class KillTrigger(Enum):
    """Types of kill switch triggers."""
    DAILY_LOSS = "daily_loss"
    WEEKLY_LOSS = "weekly_loss"
    DRAWDOWN = "drawdown"
    FILL_RATE_DROP = "fill_rate_drop"
    LATENCY_SPIKE = "latency_spike"
    ERROR_RATE = "error_rate"
    MANUAL = "manual"
    CONSECUTIVE_LOSSES = "consecutive_losses"


@dataclass
class TriggerEvent:
    """Record of a trigger activation."""
    trigger: KillTrigger
    timestamp: datetime
    value: float
    threshold: float
    message: str

    def to_dict(self) -> Dict:
        return {
            "trigger": self.trigger.value,
            "timestamp": self.timestamp.isoformat(),
            "value": self.value,
            "threshold": self.threshold,
            "message": self.message,
        }


@dataclass
class MetricsSnapshot:
    """Current system metrics for kill switch evaluation."""
    # PnL metrics
    daily_pnl: float = 0.0
    weekly_pnl: float = 0.0
    bankroll: float = 1000.0
    peak_bankroll: float = 1000.0

    # Operational metrics
    fill_rate: float = 1.0  # Last N bets
    avg_latency_ms: float = 500.0
    error_rate: float = 0.0  # Errors / total requests

    # Bet metrics
    consecutive_losses: int = 0
    bets_today: int = 0

    timestamp: datetime = field(default_factory=datetime.utcnow)


# Default trigger thresholds
DEFAULT_TRIGGERS = {
    KillTrigger.DAILY_LOSS: -0.05,       # -5% of bankroll
    KillTrigger.WEEKLY_LOSS: -0.10,      # -10% of bankroll
    KillTrigger.DRAWDOWN: -0.15,         # -15% from peak
    KillTrigger.FILL_RATE_DROP: 0.50,    # < 50% fill rate
    KillTrigger.LATENCY_SPIKE: 10000.0,  # > 10s average latency
    KillTrigger.ERROR_RATE: 0.10,        # > 10% error rate
    KillTrigger.CONSECUTIVE_LOSSES: 10,  # 10 losses in a row
}


class KillSwitch:
    """
    Emergency stop system.

    Monitors system health and freezes operations when thresholds breached.

    Usage:
        kill_switch = KillSwitch(bankroll=1000)

        # Check on each bet/decision
        metrics = MetricsSnapshot(daily_pnl=-60, bankroll=940, ...)
        if kill_switch.check(metrics):
            # System frozen, stop all operations
            pass

        # Manual controls
        kill_switch.freeze(reason="maintenance")
        kill_switch.unfreeze(approver="admin")
    """

    def __init__(
        self,
        bankroll: float = 1000.0,
        triggers: Optional[Dict[KillTrigger, float]] = None,
        on_freeze: Optional[Callable[[TriggerEvent], None]] = None,
    ):
        self.initial_bankroll = bankroll
        self.triggers = triggers or DEFAULT_TRIGGERS.copy()
        self.on_freeze = on_freeze

        self.state = SystemState.RUNNING
        self.frozen_at: Optional[datetime] = None
        self.frozen_reason: Optional[TriggerEvent] = None

        self.trigger_history: List[TriggerEvent] = []
        self.logger = logging.getLogger("kill_switch")

    def check(self, metrics: MetricsSnapshot) -> bool:
        """
        Check metrics against all triggers.

        Args:
            metrics: Current system metrics

        Returns:
            True if system was frozen (trigger activated)
        """
        if self.state != SystemState.RUNNING:
            return True  # Already frozen

        for trigger, threshold in self.triggers.items():
            triggered, event = self._check_trigger(trigger, threshold, metrics)
            if triggered:
                self._activate_freeze(event)
                return True

        return False

    def _check_trigger(
        self,
        trigger: KillTrigger,
        threshold: float,
        metrics: MetricsSnapshot,
    ) -> tuple[bool, Optional[TriggerEvent]]:
        """Check a single trigger condition."""
        value = None
        triggered = False
        message = ""

        if trigger == KillTrigger.DAILY_LOSS:
            value = metrics.daily_pnl / metrics.bankroll if metrics.bankroll > 0 else 0
            triggered = value < threshold
            message = f"Daily loss {value:.1%} exceeds limit {threshold:.1%}"

        elif trigger == KillTrigger.WEEKLY_LOSS:
            value = metrics.weekly_pnl / metrics.bankroll if metrics.bankroll > 0 else 0
            triggered = value < threshold
            message = f"Weekly loss {value:.1%} exceeds limit {threshold:.1%}"

        elif trigger == KillTrigger.DRAWDOWN:
            if metrics.peak_bankroll > 0:
                value = (metrics.bankroll - metrics.peak_bankroll) / metrics.peak_bankroll
            else:
                value = 0
            triggered = value < threshold
            message = f"Drawdown {value:.1%} exceeds limit {threshold:.1%}"

        elif trigger == KillTrigger.FILL_RATE_DROP:
            value = metrics.fill_rate
            triggered = value < threshold
            message = f"Fill rate {value:.1%} below minimum {threshold:.1%}"

        elif trigger == KillTrigger.LATENCY_SPIKE:
            value = metrics.avg_latency_ms
            triggered = value > threshold
            message = f"Latency {value:.0f}ms exceeds limit {threshold:.0f}ms"

        elif trigger == KillTrigger.ERROR_RATE:
            value = metrics.error_rate
            triggered = value > threshold
            message = f"Error rate {value:.1%} exceeds limit {threshold:.1%}"

        elif trigger == KillTrigger.CONSECUTIVE_LOSSES:
            value = metrics.consecutive_losses
            triggered = value >= threshold
            message = f"Consecutive losses {value} exceeds limit {threshold}"

        if triggered and value is not None:
            event = TriggerEvent(
                trigger=trigger,
                timestamp=datetime.utcnow(),
                value=value,
                threshold=threshold,
                message=message,
            )
            return True, event

        return False, None

    def _activate_freeze(self, event: TriggerEvent) -> None:
        """Activate freeze state."""
        self.state = SystemState.FROZEN
        self.frozen_at = datetime.utcnow()
        self.frozen_reason = event
        self.trigger_history.append(event)

        self.logger.critical(f"KILL SWITCH ACTIVATED: {event.message}")

        if self.on_freeze:
            try:
                self.on_freeze(event)
            except Exception as e:
                self.logger.error(f"on_freeze callback failed: {e}")

    def freeze(self, reason: str = "manual") -> None:
        """Manually freeze the system."""
        event = TriggerEvent(
            trigger=KillTrigger.MANUAL,
            timestamp=datetime.utcnow(),
            value=0,
            threshold=0,
            message=f"Manual freeze: {reason}",
        )
        self._activate_freeze(event)

    def unfreeze(self, approver: str = "unknown") -> bool:
        """
        Unfreeze the system (requires approval).

        Args:
            approver: Who approved the unfreeze

        Returns:
            True if successfully unfrozen
        """
        if self.state != SystemState.FROZEN:
            return False

        self.logger.info(f"System unfrozen by {approver}")
        self.state = SystemState.RUNNING
        self.frozen_at = None
        self.frozen_reason = None

        return True

    def set_maintenance(self) -> None:
        """Put system in maintenance mode."""
        self.state = SystemState.MAINTENANCE
        self.logger.info("System in maintenance mode")

    def end_maintenance(self) -> None:
        """End maintenance mode."""
        if self.state == SystemState.MAINTENANCE:
            self.state = SystemState.RUNNING
            self.logger.info("Maintenance mode ended")

    def is_running(self) -> bool:
        """Check if system is running."""
        return self.state == SystemState.RUNNING

    def is_frozen(self) -> bool:
        """Check if system is frozen."""
        return self.state == SystemState.FROZEN

    def get_status(self) -> Dict:
        """Get current kill switch status."""
        return {
            "state": self.state.value,
            "frozen_at": self.frozen_at.isoformat() if self.frozen_at else None,
            "frozen_reason": self.frozen_reason.to_dict() if self.frozen_reason else None,
            "triggers": {t.value: v for t, v in self.triggers.items()},
            "history_count": len(self.trigger_history),
        }

    def update_trigger(self, trigger: KillTrigger, threshold: float) -> None:
        """Update a trigger threshold."""
        self.triggers[trigger] = threshold
        self.logger.info(f"Updated trigger {trigger.value} to {threshold}")

    def get_history(self, limit: int = 10) -> List[Dict]:
        """Get recent trigger history."""
        return [e.to_dict() for e in self.trigger_history[-limit:]]


class MetricsTracker:
    """
    Track metrics for kill switch evaluation.

    Maintains rolling windows of performance data.
    """

    def __init__(self, bankroll: float = 1000.0):
        self.bankroll = bankroll
        self.peak_bankroll = bankroll
        self.initial_bankroll = bankroll

        self.daily_pnl = 0.0
        self.weekly_pnl = 0.0
        self.day_start = datetime.utcnow().date()
        self.week_start = datetime.utcnow().date()

        self.recent_fills: List[bool] = []
        self.recent_latencies: List[float] = []
        self.recent_errors: List[bool] = []
        self.consecutive_losses = 0

        self.window_size = 20  # Rolling window for rates

    def record_bet(
        self,
        pnl: float,
        filled: bool,
        latency_ms: float,
        won: bool,
    ) -> None:
        """Record a bet outcome."""
        # Update bankroll
        self.bankroll += pnl
        if self.bankroll > self.peak_bankroll:
            self.peak_bankroll = self.bankroll

        # Update PnL
        self._check_day_week_reset()
        self.daily_pnl += pnl
        self.weekly_pnl += pnl

        # Update rolling metrics
        self.recent_fills.append(filled)
        self.recent_fills = self.recent_fills[-self.window_size:]

        self.recent_latencies.append(latency_ms)
        self.recent_latencies = self.recent_latencies[-self.window_size:]

        # Consecutive losses
        if not won:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

    def record_error(self) -> None:
        """Record an error."""
        self.recent_errors.append(True)
        self.recent_errors = self.recent_errors[-self.window_size:]

    def record_success(self) -> None:
        """Record a successful operation (no error)."""
        self.recent_errors.append(False)
        self.recent_errors = self.recent_errors[-self.window_size:]

    def _check_day_week_reset(self) -> None:
        """Reset daily/weekly PnL at boundaries."""
        today = datetime.utcnow().date()

        if today != self.day_start:
            self.daily_pnl = 0.0
            self.day_start = today

        # Simple week detection (Monday = 0)
        if today.weekday() == 0 and today != self.week_start:
            self.weekly_pnl = 0.0
            self.week_start = today

    def get_snapshot(self) -> MetricsSnapshot:
        """Get current metrics snapshot."""
        fill_rate = (
            sum(self.recent_fills) / len(self.recent_fills)
            if self.recent_fills else 1.0
        )
        avg_latency = (
            sum(self.recent_latencies) / len(self.recent_latencies)
            if self.recent_latencies else 500.0
        )
        error_rate = (
            sum(self.recent_errors) / len(self.recent_errors)
            if self.recent_errors else 0.0
        )

        return MetricsSnapshot(
            daily_pnl=self.daily_pnl,
            weekly_pnl=self.weekly_pnl,
            bankroll=self.bankroll,
            peak_bankroll=self.peak_bankroll,
            fill_rate=fill_rate,
            avg_latency_ms=avg_latency,
            error_rate=error_rate,
            consecutive_losses=self.consecutive_losses,
        )
