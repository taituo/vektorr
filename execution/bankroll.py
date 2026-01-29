"""
Centralized Bankroll - Single source of truth for system balance.

Provides subscription mechanism for components to sync on bankroll changes.

Usage:
    bankroll = Bankroll(initial=1000.0)

    # Subscribe to changes
    bankroll.subscribe(lambda old, new, reason: print(f"Bankroll: {old} -> {new}"))

    # Update balance
    bankroll.add(50.0, reason="WIN match123")
    bankroll.subtract(10.0, reason="LOSS match456")

    # Get current value
    print(bankroll.current)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, List, Optional


class ChangeReason(Enum):
    """Reasons for bankroll changes."""
    BET_WIN = "bet_win"
    BET_LOSS = "bet_loss"
    BET_REFUND = "bet_refund"
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    ADJUSTMENT = "adjustment"
    FEE = "fee"


@dataclass
class BankrollChange:
    """Record of a bankroll change."""
    timestamp: datetime
    old_value: float
    new_value: float
    delta: float
    reason: ChangeReason
    details: str = ""
    match_id: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "old_value": self.old_value,
            "new_value": self.new_value,
            "delta": self.delta,
            "reason": self.reason.value,
            "details": self.details,
            "match_id": self.match_id,
        }


# Type for change callbacks
ChangeCallback = Callable[[float, float, BankrollChange], None]


class Bankroll:
    """
    Centralized bankroll management.

    Single source of truth for system balance with change notifications.
    """

    def __init__(self, initial: float = 1000.0):
        self._balance = initial
        self._initial = initial
        self._peak = initial
        self._low = initial

        self._subscribers: List[ChangeCallback] = []
        self._history: List[BankrollChange] = []
        self._logger = logging.getLogger("bankroll")

    @property
    def current(self) -> float:
        """Get current balance."""
        return self._balance

    @property
    def initial(self) -> float:
        """Get initial balance."""
        return self._initial

    @property
    def peak(self) -> float:
        """Get peak balance (high water mark)."""
        return self._peak

    @property
    def low(self) -> float:
        """Get lowest balance."""
        return self._low

    @property
    def total_pnl(self) -> float:
        """Get total profit/loss from initial."""
        return self._balance - self._initial

    @property
    def drawdown(self) -> float:
        """Get current drawdown from peak."""
        if self._peak == 0:
            return 0.0
        return (self._balance - self._peak) / self._peak

    @property
    def roi(self) -> float:
        """Get return on investment."""
        if self._initial == 0:
            return 0.0
        return (self._balance - self._initial) / self._initial

    def subscribe(self, callback: ChangeCallback) -> None:
        """
        Subscribe to bankroll changes.

        Callback receives (old_value, new_value, change_record).
        """
        self._subscribers.append(callback)

    def unsubscribe(self, callback: ChangeCallback) -> None:
        """Remove a subscriber."""
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    def add(
        self,
        amount: float,
        reason: ChangeReason = ChangeReason.ADJUSTMENT,
        details: str = "",
        match_id: Optional[str] = None,
    ) -> float:
        """
        Add to balance.

        Returns new balance.
        """
        if amount < 0:
            raise ValueError("Use subtract() for negative amounts")

        old = self._balance
        self._balance += amount

        self._update_watermarks()
        self._record_change(old, reason, details, match_id)

        return self._balance

    def subtract(
        self,
        amount: float,
        reason: ChangeReason = ChangeReason.ADJUSTMENT,
        details: str = "",
        match_id: Optional[str] = None,
    ) -> float:
        """
        Subtract from balance.

        Returns new balance. Does not prevent negative balance.
        """
        if amount < 0:
            raise ValueError("Use add() for positive amounts")

        old = self._balance
        self._balance -= amount

        self._update_watermarks()
        self._record_change(old, reason, details, match_id)

        return self._balance

    def settle_bet(
        self,
        pnl: float,
        match_id: Optional[str] = None,
        details: str = "",
    ) -> float:
        """
        Settle a bet with profit/loss.

        Convenience method that handles win/loss/refund.
        """
        if pnl > 0:
            return self.add(pnl, ChangeReason.BET_WIN, details, match_id)
        elif pnl < 0:
            return self.subtract(abs(pnl), ChangeReason.BET_LOSS, details, match_id)
        else:
            # Zero PnL - refund
            self._record_change(self._balance, ChangeReason.BET_REFUND, details, match_id)
            return self._balance

    def set(
        self,
        value: float,
        reason: ChangeReason = ChangeReason.ADJUSTMENT,
        details: str = "",
    ) -> float:
        """
        Set balance to specific value.

        Use sparingly - prefer add/subtract for auditing.
        """
        old = self._balance
        self._balance = value

        self._update_watermarks()
        self._record_change(old, reason, details, None)

        return self._balance

    def _update_watermarks(self) -> None:
        """Update peak and low watermarks."""
        if self._balance > self._peak:
            self._peak = self._balance
        if self._balance < self._low:
            self._low = self._balance

    def _record_change(
        self,
        old_value: float,
        reason: ChangeReason,
        details: str,
        match_id: Optional[str],
    ) -> None:
        """Record change and notify subscribers."""
        change = BankrollChange(
            timestamp=datetime.utcnow(),
            old_value=old_value,
            new_value=self._balance,
            delta=self._balance - old_value,
            reason=reason,
            details=details,
            match_id=match_id,
        )

        self._history.append(change)

        # Log
        self._logger.info(
            f"Bankroll: {old_value:.2f} -> {self._balance:.2f} "
            f"({change.delta:+.2f}) [{reason.value}] {details}"
        )

        # Notify subscribers
        for callback in self._subscribers:
            try:
                callback(old_value, self._balance, change)
            except Exception as e:
                self._logger.error(f"Subscriber callback failed: {e}")

    def get_history(self, limit: int = 50) -> List[Dict]:
        """Get recent change history."""
        return [c.to_dict() for c in self._history[-limit:]]

    def get_status(self) -> Dict:
        """Get current bankroll status."""
        return {
            "current": self._balance,
            "initial": self._initial,
            "peak": self._peak,
            "low": self._low,
            "total_pnl": self.total_pnl,
            "roi": f"{self.roi:.2%}",
            "drawdown": f"{self.drawdown:.2%}",
            "changes_count": len(self._history),
        }

    def reset(self, initial: Optional[float] = None) -> None:
        """Reset bankroll to initial value."""
        self._balance = initial if initial is not None else self._initial
        self._initial = self._balance
        self._peak = self._balance
        self._low = self._balance
        self._history = []
        self._logger.info(f"Bankroll reset to {self._balance}")


# Global singleton
_bankroll: Optional[Bankroll] = None


def get_bankroll(initial: float = 1000.0) -> Bankroll:
    """Get or create the global bankroll instance."""
    global _bankroll
    if _bankroll is None:
        _bankroll = Bankroll(initial=initial)
    return _bankroll


def sync_metrics_tracker(tracker: 'MetricsTracker', bankroll: Bankroll) -> None:
    """
    Sync a MetricsTracker with the centralized bankroll.

    Subscribes to bankroll changes and updates tracker accordingly.
    """
    def on_change(old: float, new: float, change: BankrollChange):
        tracker.bankroll = new
        if new > tracker.peak_bankroll:
            tracker.peak_bankroll = new

    bankroll.subscribe(on_change)

    # Initial sync
    tracker.bankroll = bankroll.current
    tracker.peak_bankroll = bankroll.peak
