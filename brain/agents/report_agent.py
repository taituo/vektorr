"""
Report Agent - Phase 3

Generates periodic performance reports.

Responsibilities:
- Daily performance summaries
- Weekly trend analysis
- Gate statistics
- CLV tracking
- Email/Slack/Telegram delivery
"""

import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
from enum import Enum

from .base import BaseAgent, AgentMessage


class ReportPeriod(Enum):
    """Report time periods."""
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"


@dataclass
class PerformanceMetrics:
    """Performance metrics for a period."""
    period: ReportPeriod
    start_time: datetime
    end_time: datetime

    # Volume
    total_decisions: int = 0
    total_bets: int = 0
    total_wins: int = 0
    total_losses: int = 0

    # Financial
    total_staked: float = 0.0
    total_pnl: float = 0.0
    roi: float = 0.0

    # Quality
    clv_mean: Optional[float] = None
    clv_positive_pct: Optional[float] = None
    fill_rate: float = 1.0

    # Gates
    gate_stats: Dict[str, int] = field(default_factory=dict)

    # Streaks
    max_win_streak: int = 0
    max_loss_streak: int = 0
    current_streak: int = 0

    def to_dict(self) -> Dict:
        return {
            "period": self.period.value,
            "start": self.start_time.isoformat(),
            "end": self.end_time.isoformat(),
            "decisions": self.total_decisions,
            "bets": self.total_bets,
            "wins": self.total_wins,
            "losses": self.total_losses,
            "win_rate": f"{self.total_wins / self.total_bets:.1%}" if self.total_bets else "N/A",
            "staked": round(self.total_staked, 2),
            "pnl": round(self.total_pnl, 2),
            "roi": f"{self.roi:.2%}",
            "clv_mean": f"{self.clv_mean:.4f}" if self.clv_mean else "N/A",
            "clv_positive_pct": f"{self.clv_positive_pct:.1%}" if self.clv_positive_pct else "N/A",
            "fill_rate": f"{self.fill_rate:.1%}",
            "gates": self.gate_stats,
            "max_win_streak": self.max_win_streak,
            "max_loss_streak": self.max_loss_streak,
        }


@dataclass
class DailyReport:
    """Daily performance report."""
    date: datetime
    metrics: PerformanceMetrics
    alerts_count: int = 0
    notable_events: List[str] = field(default_factory=list)

    def to_text(self) -> str:
        """Generate text report."""
        m = self.metrics
        lines = [
            f"=== VEKTORR DAILY REPORT ===",
            f"Date: {self.date.strftime('%Y-%m-%d')}",
            "",
            "VOLUME",
            f"  Decisions: {m.total_decisions}",
            f"  Bets: {m.total_bets} ({m.total_wins}W / {m.total_losses}L)",
            f"  Win Rate: {m.total_wins / m.total_bets:.1%}" if m.total_bets else "  Win Rate: N/A",
            "",
            "FINANCIAL",
            f"  Staked: ${m.total_staked:.2f}",
            f"  P&L: ${m.total_pnl:+.2f}",
            f"  ROI: {m.roi:.2%}",
            "",
            "QUALITY",
            f"  CLV Mean: {m.clv_mean:.4f}" if m.clv_mean else "  CLV Mean: N/A",
            f"  CLV Positive: {m.clv_positive_pct:.1%}" if m.clv_positive_pct else "  CLV Positive: N/A",
            f"  Fill Rate: {m.fill_rate:.1%}",
            "",
            "GATES",
        ]

        for gate, count in sorted(m.gate_stats.items(), key=lambda x: -x[1]):
            lines.append(f"  {gate}: {count}")

        if self.notable_events:
            lines.append("")
            lines.append("NOTABLE EVENTS")
            for event in self.notable_events:
                lines.append(f"  - {event}")

        if self.alerts_count > 0:
            lines.append("")
            lines.append(f"ALERTS: {self.alerts_count} triggered")

        return "\n".join(lines)

    def to_dict(self) -> Dict:
        return {
            "date": self.date.isoformat(),
            "metrics": self.metrics.to_dict(),
            "alerts_count": self.alerts_count,
            "notable_events": self.notable_events,
        }


# Type for report delivery callback
ReportCallback = Callable[[DailyReport], None]


class ReportAgent(BaseAgent):
    """
    Performance reporting agent.

    Generates and delivers periodic reports.

    Usage:
        report = ReportAgent("reporter", config={
            "daily_hour": 23,  # Generate at 23:00
            "weekly_day": 0,   # Monday
        })

        # Register delivery callback
        report.add_delivery(lambda r: send_telegram(r.to_text()))

        report.start()

        # Feed data
        report.record_decision(decision_dict)
        report.record_outcome(decision_id, won=True, pnl=15.0)
    """

    def __init__(self, agent_id: str = "reporter", config: Optional[Dict] = None):
        super().__init__(agent_id, config)

        self.daily_hour = self.config.get("daily_hour", 23)
        self.weekly_day = self.config.get("weekly_day", 0)  # Monday

        # Data storage
        self._decisions: List[Dict] = []
        self._outcomes: Dict[str, Dict] = {}  # decision_id -> outcome
        self._alerts: List[Dict] = []

        # Reports
        self._daily_reports: List[DailyReport] = []
        self._last_daily: Optional[datetime] = None

        # Delivery callbacks
        self._delivery_callbacks: List[ReportCallback] = []

    def process(self) -> None:
        """Check if reports need to be generated."""
        now = datetime.utcnow()

        # Daily report
        if self._should_generate_daily(now):
            report = self._generate_daily_report(now - timedelta(days=1))
            self._deliver_report(report)
            self._last_daily = now

    def on_message(self, message: AgentMessage) -> Optional[AgentMessage]:
        """Handle incoming messages."""
        if message.type == "alert":
            self._alerts.append(message.payload)

        elif message.type == "report_request":
            period = message.payload.get("period", "daily")
            if period == "daily":
                report = self._generate_daily_report(datetime.utcnow())
                return AgentMessage(
                    type="report_response",
                    payload=report.to_dict(),
                )
        return None

    def add_delivery(self, callback: ReportCallback) -> None:
        """Add a report delivery callback."""
        self._delivery_callbacks.append(callback)

    def record_decision(self, decision: Dict) -> None:
        """Record a decision for reporting."""
        self._decisions.append({
            **decision,
            "recorded_at": datetime.utcnow().isoformat(),
        })

        # Keep last 7 days
        cutoff = datetime.utcnow() - timedelta(days=7)
        self._decisions = [
            d for d in self._decisions
            if datetime.fromisoformat(d.get("recorded_at", d.get("timestamp", cutoff.isoformat()))) > cutoff
        ]

    def record_outcome(
        self,
        decision_id: str,
        won: bool,
        pnl: float,
        clv: Optional[float] = None,
    ) -> None:
        """Record a decision outcome."""
        self._outcomes[decision_id] = {
            "won": won,
            "pnl": pnl,
            "clv": clv,
            "settled_at": datetime.utcnow().isoformat(),
        }

    def _should_generate_daily(self, now: datetime) -> bool:
        """Check if daily report should be generated."""
        if self._last_daily is None:
            return now.hour >= self.daily_hour

        # Generate if past daily_hour and not generated today
        return (
            now.hour >= self.daily_hour and
            now.date() > self._last_daily.date()
        )

    def _generate_daily_report(self, date: datetime) -> DailyReport:
        """Generate daily performance report."""
        start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)

        # Filter decisions for this day
        day_decisions = [
            d for d in self._decisions
            if start <= datetime.fromisoformat(d.get("timestamp", start.isoformat())) < end
        ]

        # Calculate metrics
        metrics = self._calculate_metrics(day_decisions, ReportPeriod.DAILY, start, end)

        # Count alerts for this day
        day_alerts = [
            a for a in self._alerts
            if start <= datetime.fromisoformat(a.get("timestamp", start.isoformat())) < end
        ]

        # Notable events
        notable = []
        if metrics.roi > 0.05:
            notable.append(f"Strong day: {metrics.roi:.1%} ROI")
        if metrics.roi < -0.05:
            notable.append(f"Difficult day: {metrics.roi:.1%} ROI")
        if metrics.max_win_streak >= 5:
            notable.append(f"Win streak: {metrics.max_win_streak} consecutive wins")
        if metrics.max_loss_streak >= 5:
            notable.append(f"Loss streak: {metrics.max_loss_streak} consecutive losses")

        report = DailyReport(
            date=date,
            metrics=metrics,
            alerts_count=len(day_alerts),
            notable_events=notable,
        )

        self._daily_reports.append(report)
        self.logger.info(f"Generated daily report for {date.strftime('%Y-%m-%d')}")

        return report

    def _calculate_metrics(
        self,
        decisions: List[Dict],
        period: ReportPeriod,
        start: datetime,
        end: datetime,
    ) -> PerformanceMetrics:
        """Calculate performance metrics from decisions."""
        metrics = PerformanceMetrics(
            period=period,
            start_time=start,
            end_time=end,
        )

        metrics.total_decisions = len(decisions)

        # Gate statistics
        for d in decisions:
            reason = d.get("reason", "UNKNOWN")
            metrics.gate_stats[reason] = metrics.gate_stats.get(reason, 0) + 1

        # Filter to bets only
        bets = [d for d in decisions if d.get("can_bet") or d.get("action") == "BET"]
        metrics.total_bets = len(bets)

        if not bets:
            return metrics

        # Match with outcomes
        wins = []
        losses = []
        clvs = []
        fills = []

        for bet in bets:
            decision_id = bet.get("decision_id")
            outcome = self._outcomes.get(decision_id)

            if outcome:
                if outcome["won"]:
                    wins.append(bet)
                    metrics.total_wins += 1
                else:
                    losses.append(bet)
                    metrics.total_losses += 1

                metrics.total_pnl += outcome.get("pnl", 0)

                if outcome.get("clv") is not None:
                    clvs.append(outcome["clv"])

            # Track fills
            if bet.get("filled") is not None:
                fills.append(bet.get("filled"))

            metrics.total_staked += bet.get("stake", 0)

        # Calculate rates
        if metrics.total_staked > 0:
            metrics.roi = metrics.total_pnl / metrics.total_staked

        if clvs:
            metrics.clv_mean = statistics.mean(clvs)
            metrics.clv_positive_pct = len([c for c in clvs if c > 0]) / len(clvs)

        if fills:
            metrics.fill_rate = sum(fills) / len(fills)

        # Calculate streaks
        outcomes_ordered = []
        for bet in bets:
            decision_id = bet.get("decision_id")
            outcome = self._outcomes.get(decision_id)
            if outcome:
                outcomes_ordered.append(outcome["won"])

        if outcomes_ordered:
            metrics.max_win_streak, metrics.max_loss_streak = self._calculate_streaks(outcomes_ordered)

        return metrics

    def _calculate_streaks(self, outcomes: List[bool]) -> tuple:
        """Calculate max win and loss streaks."""
        max_win = 0
        max_loss = 0
        current_win = 0
        current_loss = 0

        for won in outcomes:
            if won:
                current_win += 1
                current_loss = 0
                max_win = max(max_win, current_win)
            else:
                current_loss += 1
                current_win = 0
                max_loss = max(max_loss, current_loss)

        return max_win, max_loss

    def _deliver_report(self, report: DailyReport) -> None:
        """Deliver report via callbacks."""
        # Broadcast via message bus
        self.send_message(AgentMessage(
            type="daily_report",
            payload=report.to_dict(),
        ))

        # Call delivery callbacks
        for callback in self._delivery_callbacks:
            try:
                callback(report)
            except Exception as e:
                self.logger.error(f"Report delivery failed: {e}")

    def get_daily_report(self, date: Optional[datetime] = None) -> Optional[DailyReport]:
        """Get daily report for a specific date."""
        if date is None:
            date = datetime.utcnow()

        target_date = date.date()
        for report in self._daily_reports:
            if report.date.date() == target_date:
                return report

        # Generate on demand
        return self._generate_daily_report(date)

    def get_recent_reports(self, limit: int = 7) -> List[Dict]:
        """Get recent daily reports."""
        return [r.to_dict() for r in self._daily_reports[-limit:]]

    def get_status(self) -> Dict:
        """Get reporter status."""
        return {
            "decisions_tracked": len(self._decisions),
            "outcomes_tracked": len(self._outcomes),
            "reports_generated": len(self._daily_reports),
            "last_daily": self._last_daily.isoformat() if self._last_daily else None,
            "delivery_callbacks": len(self._delivery_callbacks),
        }
