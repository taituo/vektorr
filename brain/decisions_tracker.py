"""
Decisions Tracker for Phase 0 CLV measurement.

Tracks all decisions (BET and NO_BET) with calibration-relevant fields.
Supports updating with closing odds for CLV calculation.

Storage: JSONL file (can be migrated to QuestDB later).
"""

import json
import os
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from pathlib import Path

try:
    from calibration import (
        CalibrationMetrics,
        CLVCalculator,
        ROICalculator,
        PredictionOutcome,
        ValidationReport,
    )
except ImportError:
    from brain.calibration import (
        CalibrationMetrics,
        CLVCalculator,
        ROICalculator,
        PredictionOutcome,
        ValidationReport,
    )


@dataclass
class Decision:
    """A single decision record for calibration tracking."""
    # Identity
    decision_id: str
    match_id: str
    timestamp: datetime

    # Match state
    minute: int
    tps_label: str
    xg_10m: float
    latency_p95: float

    # Decision
    can_bet: bool
    reason: str

    # Model outputs (for calibration)
    p_model: float
    ev: float

    # Odds
    market: str
    selection: str
    odds_at_decision: float
    odds_at_close: Optional[float] = None  # Updated later for CLV

    # Outcome (filled after match)
    outcome: Optional[int] = None  # 1 = event occurred, 0 = did not
    settled: bool = False

    # Execution (if bet was placed)
    bet_placed: bool = False
    stake: float = 0.0
    price_filled: Optional[float] = None
    pnl: Optional[float] = None

    # Metadata
    clv: Optional[float] = None  # Calculated when odds_at_close is set

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON serialization."""
        d = asdict(self)
        d['timestamp'] = self.timestamp.isoformat()
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'Decision':
        """Create from dict (JSON deserialization)."""
        d['timestamp'] = datetime.fromisoformat(d['timestamp'])
        return cls(**d)


class DecisionsTracker:
    """
    Tracks decisions for Phase 0 validation metrics.

    Usage:
        tracker = DecisionsTracker("decisions.jsonl")

        # Record a decision
        decision_id = tracker.record_decision(
            match_id="m123",
            minute=45,
            tps_label="PRESS",
            ...
        )

        # Update with closing odds (call 2-5 min after decision)
        tracker.update_closing_odds(decision_id, closing_odds=1.85)

        # Update outcome after match
        tracker.update_outcome(decision_id, outcome=1, pnl=10.0)

        # Get validation report
        report = tracker.get_validation_report()
    """

    def __init__(self, path: str = "decisions_tracker.jsonl"):
        self.path = Path(path)
        self._decisions: Dict[str, Decision] = {}
        self._load()

    def _load(self) -> None:
        """Load existing decisions from file."""
        if not self.path.exists():
            return

        with open(self.path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    decision = Decision.from_dict(d)
                    self._decisions[decision.decision_id] = decision
                except Exception:
                    pass  # Skip malformed lines

    def _save_decision(self, decision: Decision) -> None:
        """Append decision to file."""
        with open(self.path, 'a') as f:
            f.write(json.dumps(decision.to_dict()) + "\n")

    def _rewrite_all(self) -> None:
        """Rewrite entire file (for updates)."""
        with open(self.path, 'w') as f:
            for decision in self._decisions.values():
                f.write(json.dumps(decision.to_dict()) + "\n")

    def record_decision(
        self,
        match_id: str,
        minute: int,
        tps_label: str,
        xg_10m: float,
        latency_p95: float,
        can_bet: bool,
        reason: str,
        p_model: float,
        ev: float,
        market: str,
        selection: str,
        odds_at_decision: float,
        bet_placed: bool = False,
        stake: float = 0.0,
        price_filled: Optional[float] = None,
    ) -> str:
        """
        Record a new decision.

        Returns:
            decision_id for later updates
        """
        timestamp = datetime.now(timezone.utc)
        decision_id = f"{match_id}_{timestamp.strftime('%Y%m%d%H%M%S%f')}"

        decision = Decision(
            decision_id=decision_id,
            match_id=match_id,
            timestamp=timestamp,
            minute=minute,
            tps_label=tps_label,
            xg_10m=xg_10m,
            latency_p95=latency_p95,
            can_bet=can_bet,
            reason=reason,
            p_model=p_model,
            ev=ev,
            market=market,
            selection=selection,
            odds_at_decision=odds_at_decision,
            bet_placed=bet_placed,
            stake=stake,
            price_filled=price_filled,
        )

        self._decisions[decision_id] = decision
        self._save_decision(decision)

        return decision_id

    def update_closing_odds(self, decision_id: str, closing_odds: float) -> bool:
        """
        Update a decision with closing odds for CLV calculation.

        Call this 2-5 minutes after the decision was made.

        Returns:
            True if updated, False if decision not found
        """
        if decision_id not in self._decisions:
            return False

        decision = self._decisions[decision_id]
        decision.odds_at_close = closing_odds

        # Calculate CLV
        if closing_odds > 0 and decision.odds_at_decision > 0:
            decision.clv = CLVCalculator.calculate_clv(
                decision.odds_at_decision,
                closing_odds
            )

        self._rewrite_all()
        return True

    def update_outcome(
        self,
        decision_id: str,
        outcome: int,
        pnl: Optional[float] = None
    ) -> bool:
        """
        Update a decision with the outcome after match settlement.

        Args:
            decision_id: The decision to update
            outcome: 1 if event occurred, 0 if not
            pnl: Profit/loss if bet was placed

        Returns:
            True if updated, False if decision not found
        """
        if decision_id not in self._decisions:
            return False

        decision = self._decisions[decision_id]
        decision.outcome = outcome
        decision.settled = True

        if pnl is not None:
            decision.pnl = pnl

        self._rewrite_all()
        return True

    def get_pending_clv_updates(self, max_age_minutes: int = 10) -> List[Decision]:
        """
        Get decisions that need closing odds update.

        Returns decisions that:
        - Have no closing odds yet
        - Are between 2 and max_age_minutes old
        """
        now = datetime.now(timezone.utc)
        min_age = timedelta(minutes=2)
        max_age = timedelta(minutes=max_age_minutes)

        pending = []
        for decision in self._decisions.values():
            if decision.odds_at_close is not None:
                continue  # Already has closing odds

            age = now - decision.timestamp
            if min_age <= age <= max_age:
                pending.append(decision)

        return pending

    def get_unsettled_decisions(self) -> List[Decision]:
        """Get decisions that need outcome update."""
        return [d for d in self._decisions.values() if not d.settled]

    def get_all_decisions(self) -> List[Decision]:
        """Get all tracked decisions."""
        return list(self._decisions.values())

    def get_bet_decisions(self) -> List[Decision]:
        """Get only decisions where a bet was placed."""
        return [d for d in self._decisions.values() if d.bet_placed]

    def get_settled_bets(self) -> List[Decision]:
        """Get settled bets for metrics calculation."""
        return [d for d in self._decisions.values() if d.bet_placed and d.settled]

    def get_validation_report(self) -> Dict[str, Any]:
        """
        Generate Phase 0 validation report.

        Uses settled bets for calibration metrics.
        """
        settled = self.get_settled_bets()

        if not settled:
            return {
                'error': 'No settled bets yet',
                'total_decisions': len(self._decisions),
                'total_bets': len(self.get_bet_decisions()),
                'settled_bets': 0,
            }

        # Convert to PredictionOutcome for calibration module
        outcomes = []
        for d in settled:
            outcomes.append(PredictionOutcome(
                match_id=d.match_id,
                timestamp=d.timestamp,
                p_model=d.p_model,
                outcome=d.outcome or 0,
                odds_at_decision=d.odds_at_decision,
                odds_at_close=d.odds_at_close,
                market=d.market,
                selection=d.selection,
                stake=d.stake,
                pnl=d.pnl or 0.0,
            ))

        report = ValidationReport(outcomes)
        result = report.generate()

        # Add tracker-specific stats
        result['total_decisions'] = len(self._decisions)
        result['total_bets'] = len(self.get_bet_decisions())
        result['pending_clv'] = len(self.get_pending_clv_updates())
        result['unsettled'] = len(self.get_unsettled_decisions())

        return result

    def get_metrics_summary(self) -> Dict[str, Any]:
        """Quick metrics summary for dashboard."""
        all_decisions = self.get_all_decisions()
        bets = self.get_bet_decisions()
        settled = self.get_settled_bets()

        # Calculate CLV for bets with closing odds
        clvs = [d.clv for d in bets if d.clv is not None]

        # Calculate ROI for settled bets
        total_staked = sum(d.stake for d in settled)
        total_pnl = sum(d.pnl or 0 for d in settled)

        # Reasons breakdown
        reasons = {}
        for d in all_decisions:
            reasons[d.reason] = reasons.get(d.reason, 0) + 1

        return {
            'total_decisions': len(all_decisions),
            'total_bets': len(bets),
            'settled_bets': len(settled),
            'bet_rate': len(bets) / len(all_decisions) if all_decisions else 0,

            'clv_mean': sum(clvs) / len(clvs) if clvs else None,
            'clv_positive_pct': len([c for c in clvs if c > 0]) / len(clvs) if clvs else None,

            'roi': total_pnl / total_staked if total_staked > 0 else None,
            'total_pnl': total_pnl,
            'total_staked': total_staked,

            'reasons': reasons,
        }


# Singleton instance for easy import
_tracker: Optional[DecisionsTracker] = None


def get_tracker(path: str = "decisions_tracker.jsonl") -> DecisionsTracker:
    """Get or create the global decisions tracker."""
    global _tracker
    if _tracker is None:
        _tracker = DecisionsTracker(path)
    return _tracker
