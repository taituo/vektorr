"""
Learning Agent - Phase 3

Analyzes decisions and outcomes to suggest improvements.

Responsibilities:
- Weekly analysis of betting performance
- Pattern detection in losing bets
- Missed edge identification
- Parameter adjustment suggestions
- Auto-tuning for small changes (< 20%)
"""

import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from enum import Enum

from .base import BaseAgent, AgentMessage, AgentState


class SuggestionType(Enum):
    """Types of parameter suggestions."""
    INCREASE = "increase"
    DECREASE = "decrease"
    KEEP = "keep"


class ApprovalLevel(Enum):
    """Approval requirement for changes."""
    AUTO = "auto"           # < 10% change, auto-apply
    REVIEW = "review"       # 10-20% change, log but apply
    HUMAN = "human"         # > 20% change, requires approval


@dataclass
class ParameterSuggestion:
    """Suggested parameter change."""
    parameter: str
    current_value: float
    suggested_value: float
    change_pct: float
    confidence: float
    reason: str
    approval_level: ApprovalLevel
    evidence: Dict = field(default_factory=dict)

    @property
    def suggestion_type(self) -> SuggestionType:
        if self.suggested_value > self.current_value * 1.01:
            return SuggestionType.INCREASE
        elif self.suggested_value < self.current_value * 0.99:
            return SuggestionType.DECREASE
        return SuggestionType.KEEP

    def to_dict(self) -> Dict:
        return {
            "parameter": self.parameter,
            "current": self.current_value,
            "suggested": self.suggested_value,
            "change_pct": f"{self.change_pct:+.1f}%",
            "confidence": self.confidence,
            "reason": self.reason,
            "approval": self.approval_level.value,
            "type": self.suggestion_type.value,
        }


@dataclass
class PatternAnalysis:
    """Analysis of a detected pattern."""
    pattern_type: str
    description: str
    frequency: int
    impact: float  # ROI impact
    examples: List[Dict] = field(default_factory=list)
    suggested_action: str = ""


@dataclass
class WeeklyAnalysis:
    """Complete weekly analysis report."""
    period_start: datetime
    period_end: datetime
    total_decisions: int
    total_bets: int
    win_rate: float
    roi: float
    clv_mean: float

    patterns_detected: List[PatternAnalysis] = field(default_factory=list)
    missed_edges: List[Dict] = field(default_factory=list)
    suggestions: List[ParameterSuggestion] = field(default_factory=list)

    auto_applied: List[str] = field(default_factory=list)
    pending_human_approval: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "period": {
                "start": self.period_start.isoformat(),
                "end": self.period_end.isoformat(),
            },
            "summary": {
                "decisions": self.total_decisions,
                "bets": self.total_bets,
                "win_rate": f"{self.win_rate:.1%}",
                "roi": f"{self.roi:+.2%}",
                "clv_mean": f"{self.clv_mean:+.2%}",
            },
            "patterns": [
                {
                    "type": p.pattern_type,
                    "description": p.description,
                    "frequency": p.frequency,
                    "impact": f"{p.impact:+.2%}",
                }
                for p in self.patterns_detected
            ],
            "missed_edges_count": len(self.missed_edges),
            "suggestions": [s.to_dict() for s in self.suggestions],
            "auto_applied": self.auto_applied,
            "pending_approval": self.pending_human_approval,
        }


class LearningAgent(BaseAgent):
    """
    Self-improving analysis agent.

    Runs weekly to:
    1. Analyze all decisions and outcomes
    2. Detect patterns in losing/winning bets
    3. Identify missed opportunities
    4. Suggest parameter adjustments
    5. Auto-apply small changes, request approval for large ones

    Usage:
        agent = LearningAgent("learner", config={"analysis_day": 0})  # Monday
        agent.start()

        # Or run analysis manually
        analysis = agent.run_analysis(decisions, outcomes)
    """

    def __init__(
        self,
        agent_id: str = "learning_agent",
        config: Optional[Dict] = None,
    ):
        super().__init__(agent_id, config or {})

        # Configuration
        cfg = config or {}
        self.analysis_day = cfg.get("analysis_day", 0)  # 0=Monday
        self.auto_apply_threshold = cfg.get("auto_apply_threshold", 0.10)  # 10%
        self.review_threshold = cfg.get("review_threshold", 0.20)  # 20%

        # State
        self.last_analysis: Optional[WeeklyAnalysis] = None
        self.pending_suggestions: List[ParameterSuggestion] = []

    def process(self) -> None:
        """Check if it's time for weekly analysis."""
        now = datetime.utcnow()

        # Run analysis on configured day at midnight
        if now.weekday() == self.analysis_day and now.hour == 0:
            if self.last_analysis is None or \
               (now - self.last_analysis.period_end).days >= 7:
                self.logger.info("Starting weekly analysis")
                # Would load decisions from tracker here
                # For now, just log
                self.logger.info("Weekly analysis placeholder - needs decisions data")

    def on_message(self, message: AgentMessage) -> Optional[AgentMessage]:
        """Handle incoming messages."""
        if message.type == "request_analysis":
            # Run analysis on demand
            decisions = message.payload.get("decisions", [])
            outcomes = message.payload.get("outcomes", [])
            analysis = self.run_analysis(decisions, outcomes)
            return AgentMessage(
                type="analysis_complete",
                payload={"analysis": analysis.to_dict()},
            )

        elif message.type == "approval_response":
            # Human approved/rejected a suggestion
            suggestion_id = message.payload.get("suggestion_id")
            approved = message.payload.get("approved", False)
            self._handle_approval(suggestion_id, approved)

        return None

    def run_analysis(
        self,
        decisions: List[Dict],
        outcomes: Optional[List[Dict]] = None,
        current_params: Optional[Dict] = None,
    ) -> WeeklyAnalysis:
        """
        Run full weekly analysis.

        Args:
            decisions: List of decision records
            outcomes: List of outcome records (matched by decision_id)
            current_params: Current parameter values

        Returns:
            WeeklyAnalysis with findings and suggestions
        """
        if not decisions:
            return self._empty_analysis()

        # Match decisions with outcomes
        matched = self._match_decisions_outcomes(decisions, outcomes or [])

        # Calculate basic metrics
        metrics = self._calculate_metrics(matched)

        # Detect patterns
        patterns = self._detect_patterns(matched)

        # Find missed edges
        missed = self._find_missed_edges(decisions, outcomes or [])

        # Generate suggestions
        suggestions = self._generate_suggestions(
            metrics, patterns, missed, current_params or {}
        )

        # Determine what to auto-apply vs request approval
        auto_applied = []
        pending_approval = []

        for suggestion in suggestions:
            if suggestion.approval_level == ApprovalLevel.AUTO:
                auto_applied.append(suggestion.parameter)
            elif suggestion.approval_level == ApprovalLevel.HUMAN:
                pending_approval.append(suggestion.parameter)
                self.pending_suggestions.append(suggestion)

        # Build analysis
        now = datetime.utcnow()
        analysis = WeeklyAnalysis(
            period_start=now - timedelta(days=7),
            period_end=now,
            total_decisions=len(decisions),
            total_bets=len([d for d in decisions if d.get("action") == "BET"]),
            win_rate=metrics.get("win_rate", 0.0),
            roi=metrics.get("roi", 0.0),
            clv_mean=metrics.get("clv_mean", 0.0),
            patterns_detected=patterns,
            missed_edges=missed[:10],  # Top 10
            suggestions=suggestions,
            auto_applied=auto_applied,
            pending_human_approval=pending_approval,
        )

        self.last_analysis = analysis

        # Send notification if pending approvals
        if pending_approval:
            self.send_message(AgentMessage(
                type="approval_needed",
                payload={
                    "suggestions": [s.to_dict() for s in suggestions
                                   if s.approval_level == ApprovalLevel.HUMAN],
                },
                priority=1,
            ))

        return analysis

    def _empty_analysis(self) -> WeeklyAnalysis:
        """Return empty analysis when no data."""
        now = datetime.utcnow()
        return WeeklyAnalysis(
            period_start=now - timedelta(days=7),
            period_end=now,
            total_decisions=0,
            total_bets=0,
            win_rate=0.0,
            roi=0.0,
            clv_mean=0.0,
        )

    def _match_decisions_outcomes(
        self,
        decisions: List[Dict],
        outcomes: List[Dict],
    ) -> List[Dict]:
        """Match decisions with their outcomes."""
        outcome_map = {o.get("decision_id"): o for o in outcomes}

        matched = []
        for decision in decisions:
            decision_id = decision.get("decision_id")
            record = {**decision}
            if decision_id in outcome_map:
                record["outcome"] = outcome_map[decision_id]
            matched.append(record)

        return matched

    def _calculate_metrics(self, matched: List[Dict]) -> Dict:
        """Calculate performance metrics from matched data."""
        bets = [m for m in matched if m.get("action") == "BET" and "outcome" in m]

        if not bets:
            return {"win_rate": 0.0, "roi": 0.0, "clv_mean": 0.0}

        wins = [b for b in bets if b["outcome"].get("won", False)]
        win_rate = len(wins) / len(bets) if bets else 0.0

        # ROI
        total_staked = sum(b.get("stake", 10) for b in bets)
        total_pnl = sum(b["outcome"].get("pnl", 0) for b in bets)
        roi = total_pnl / total_staked if total_staked > 0 else 0.0

        # CLV
        clvs = [b.get("clv", 0) for b in bets if b.get("clv") is not None]
        clv_mean = statistics.mean(clvs) if clvs else 0.0

        return {
            "win_rate": win_rate,
            "roi": roi,
            "clv_mean": clv_mean,
            "total_bets": len(bets),
            "wins": len(wins),
            "losses": len(bets) - len(wins),
        }

    def _detect_patterns(self, matched: List[Dict]) -> List[PatternAnalysis]:
        """Detect patterns in betting performance."""
        patterns = []

        bets = [m for m in matched if m.get("action") == "BET" and "outcome" in m]
        if len(bets) < 10:
            return patterns

        losses = [b for b in bets if not b["outcome"].get("won", False)]

        # Pattern 1: Late game losses
        late_losses = [b for b in losses if b.get("minute", 0) >= 75]
        if len(late_losses) >= 3:
            late_loss_rate = len(late_losses) / len([b for b in bets if b.get("minute", 0) >= 75]) \
                if [b for b in bets if b.get("minute", 0) >= 75] else 0
            if late_loss_rate > 0.6:  # More than 60% losses late game
                patterns.append(PatternAnalysis(
                    pattern_type="late_game_losses",
                    description="Higher loss rate in minutes 75+",
                    frequency=len(late_losses),
                    impact=-0.05,  # Estimated
                    suggested_action="Consider reducing late game betting or tightening EV threshold",
                ))

        # Pattern 2: CHAOS state losses
        chaos_losses = [b for b in losses if b.get("tps_label") == "CHAOS"]
        if len(chaos_losses) >= 3:
            chaos_bets = [b for b in bets if b.get("tps_label") == "CHAOS"]
            if chaos_bets and len(chaos_losses) / len(chaos_bets) > 0.6:
                patterns.append(PatternAnalysis(
                    pattern_type="chaos_losses",
                    description="High loss rate during CHAOS TPS",
                    frequency=len(chaos_losses),
                    impact=-0.03,
                    suggested_action="Increase EV threshold during CHAOS or avoid",
                ))

        # Pattern 3: Low EV losses
        low_ev_losses = [b for b in losses if b.get("ev", 0) < 0.05]
        if len(low_ev_losses) >= 5:
            patterns.append(PatternAnalysis(
                pattern_type="low_ev_losses",
                description="Losses concentrated in low EV bets",
                frequency=len(low_ev_losses),
                impact=-0.02,
                suggested_action="Increase EV_MIN threshold",
            ))

        # Pattern 4: Negative CLV correlation
        clv_loss_corr = self._calculate_clv_loss_pattern(bets)
        if clv_loss_corr:
            patterns.append(clv_loss_corr)

        return patterns

    def _calculate_clv_loss_pattern(self, bets: List[Dict]) -> Optional[PatternAnalysis]:
        """Check if negative CLV correlates with losses."""
        neg_clv = [b for b in bets if b.get("clv", 0) < 0]
        if len(neg_clv) < 5:
            return None

        neg_clv_losses = [b for b in neg_clv if not b["outcome"].get("won", False)]
        loss_rate = len(neg_clv_losses) / len(neg_clv)

        if loss_rate > 0.65:
            return PatternAnalysis(
                pattern_type="negative_clv_losses",
                description="Bets with negative CLV have high loss rate",
                frequency=len(neg_clv_losses),
                impact=-0.04,
                suggested_action="CLV is predictive - consider tighter entry timing",
            )

        return None

    def _find_missed_edges(
        self,
        decisions: List[Dict],
        outcomes: List[Dict],
    ) -> List[Dict]:
        """Find NO_BET decisions that would have been profitable."""
        outcome_map = {o.get("match_id"): o for o in outcomes}
        missed = []

        no_bets = [d for d in decisions if d.get("action") == "NO_BET"]

        for decision in no_bets:
            match_id = decision.get("match_id")
            if match_id not in outcome_map:
                continue

            outcome = outcome_map[match_id]

            # Check if the selection won
            selection_won = outcome.get("selection_won", False)
            odds_at_decision = decision.get("odds", 0)

            if selection_won and odds_at_decision > 1.5:
                # Calculate hypothetical profit
                hypothetical_ev = decision.get("p_model", 0.5) * odds_at_decision - 1

                if hypothetical_ev > 0:
                    missed.append({
                        "match_id": match_id,
                        "decision_id": decision.get("decision_id"),
                        "reason": decision.get("reason"),
                        "odds": odds_at_decision,
                        "hypothetical_ev": hypothetical_ev,
                        "hypothetical_profit": odds_at_decision - 1,
                    })

        # Sort by hypothetical profit
        missed.sort(key=lambda x: x.get("hypothetical_profit", 0), reverse=True)
        return missed

    def _generate_suggestions(
        self,
        metrics: Dict,
        patterns: List[PatternAnalysis],
        missed_edges: List[Dict],
        current_params: Dict,
    ) -> List[ParameterSuggestion]:
        """Generate parameter suggestions based on analysis."""
        suggestions = []

        # Suggestion 1: EV_MIN based on low EV losses
        low_ev_pattern = next(
            (p for p in patterns if p.pattern_type == "low_ev_losses"),
            None
        )
        if low_ev_pattern:
            current_ev_min = current_params.get("EV_MIN", 0.05)
            suggested = min(0.10, current_ev_min * 1.2)  # Increase by 20%
            suggestions.append(self._make_suggestion(
                "EV_MIN",
                current_ev_min,
                suggested,
                "Low EV bets showing high loss rate",
                low_ev_pattern.impact,
            ))

        # Suggestion 2: Late game threshold
        late_pattern = next(
            (p for p in patterns if p.pattern_type == "late_game_losses"),
            None
        )
        if late_pattern:
            current_ev_min = current_params.get("EV_MIN", 0.05)
            # Suggest higher EV threshold for late game
            suggestions.append(self._make_suggestion(
                "EV_MIN_LATE",
                current_params.get("EV_MIN_LATE", current_ev_min),
                current_ev_min * 1.3,
                "Late game (75+) showing elevated loss rate",
                late_pattern.impact,
            ))

        # Suggestion 3: Based on missed edges
        if missed_edges and len(missed_edges) > 5:
            # Many missed edges might mean threshold too high
            avg_missed_ev = statistics.mean(
                [m.get("hypothetical_ev", 0) for m in missed_edges[:10]]
            )
            if avg_missed_ev > 0.03:
                current_ev_min = current_params.get("EV_MIN", 0.05)
                suggestions.append(self._make_suggestion(
                    "EV_MIN",
                    current_ev_min,
                    max(0.02, current_ev_min * 0.9),  # Decrease by 10%
                    f"Missed {len(missed_edges)} profitable opportunities",
                    0.02,  # Positive impact
                ))

        # Suggestion 4: XG threshold if ROI is negative with high volume
        if metrics.get("roi", 0) < -0.05 and metrics.get("total_bets", 0) > 30:
            current_xg = current_params.get("XG_10M_MIN", 0.2)
            suggestions.append(self._make_suggestion(
                "XG_10M_MIN",
                current_xg,
                current_xg * 1.15,  # Increase by 15%
                "Negative ROI suggests quality filter too loose",
                metrics["roi"],
            ))

        return suggestions

    def _make_suggestion(
        self,
        param: str,
        current: float,
        suggested: float,
        reason: str,
        impact: float,
    ) -> ParameterSuggestion:
        """Create a parameter suggestion with proper approval level."""
        change_pct = abs(suggested - current) / current * 100 if current != 0 else 100

        if change_pct < self.auto_apply_threshold * 100:
            approval = ApprovalLevel.AUTO
        elif change_pct < self.review_threshold * 100:
            approval = ApprovalLevel.REVIEW
        else:
            approval = ApprovalLevel.HUMAN

        confidence = min(1.0, abs(impact) * 10)  # Scale impact to confidence

        return ParameterSuggestion(
            parameter=param,
            current_value=current,
            suggested_value=round(suggested, 4),
            change_pct=change_pct,
            confidence=confidence,
            reason=reason,
            approval_level=approval,
            evidence={"impact": impact},
        )

    def _handle_approval(self, suggestion_id: str, approved: bool) -> None:
        """Handle human approval response."""
        # Find and remove from pending
        for i, suggestion in enumerate(self.pending_suggestions):
            if f"{suggestion.parameter}_{suggestion.change_pct}" == suggestion_id:
                if approved:
                    self.logger.info(f"Suggestion approved: {suggestion.parameter}")
                    # Would apply the change here
                else:
                    self.logger.info(f"Suggestion rejected: {suggestion.parameter}")
                self.pending_suggestions.pop(i)
                break


# Convenience function
def analyze_week(
    decisions: List[Dict],
    outcomes: List[Dict],
    current_params: Dict,
) -> Dict:
    """
    Quick weekly analysis.

    Args:
        decisions: List of decision records
        outcomes: List of outcome records
        current_params: Current parameter values

    Returns:
        Analysis dict
    """
    agent = LearningAgent("temp_learner")
    analysis = agent.run_analysis(decisions, outcomes, current_params)
    return analysis.to_dict()
