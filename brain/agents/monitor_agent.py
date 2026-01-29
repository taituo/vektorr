"""
Monitor Agent - Phase 3

Monitors system health and raises alerts.

Responsibilities:
- Track latency metrics
- Detect error rate spikes
- Monitor staleness (no events/decisions)
- Alert on anomalies
- Report to MessageBus
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from enum import Enum

from .base import BaseAgent, AgentMessage


class AlertLevel(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class Alert:
    """System alert."""
    level: AlertLevel
    source: str
    message: str
    metric_name: str
    metric_value: float
    threshold: float
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict:
        return {
            "level": self.level.value,
            "source": self.source,
            "message": self.message,
            "metric": self.metric_name,
            "value": self.metric_value,
            "threshold": self.threshold,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class HealthSnapshot:
    """System health snapshot."""
    timestamp: datetime
    latency_p95_ms: float
    error_rate: float
    decisions_per_hour: float
    events_per_hour: float
    last_decision_age_s: float
    last_event_age_s: float
    fill_rate: float
    active_matches: int


class MonitorAgent(BaseAgent):
    """
    System health monitoring agent.

    Tracks metrics and raises alerts when thresholds breached.

    Usage:
        monitor = MonitorAgent("monitor", config={
            "latency_warn_ms": 2000,
            "latency_crit_ms": 5000,
            "error_rate_warn": 0.05,
            "staleness_warn_s": 300,
        })
        monitor.start()

        # Update metrics
        monitor.record_latency(1500)
        monitor.record_decision()
        monitor.record_error()

        # Get alerts
        alerts = monitor.get_active_alerts()
    """

    def __init__(self, agent_id: str = "monitor", config: Optional[Dict] = None):
        super().__init__(agent_id, config)

        # Thresholds
        self.latency_warn_ms = self.config.get("latency_warn_ms", 2000)
        self.latency_crit_ms = self.config.get("latency_crit_ms", 5000)
        self.error_rate_warn = self.config.get("error_rate_warn", 0.05)
        self.error_rate_crit = self.config.get("error_rate_crit", 0.10)
        self.staleness_warn_s = self.config.get("staleness_warn_s", 300)
        self.staleness_crit_s = self.config.get("staleness_crit_s", 600)
        self.fill_rate_warn = self.config.get("fill_rate_warn", 0.70)

        # Rolling windows
        self.window_size = self.config.get("window_size", 100)
        self._latencies: List[float] = []
        self._errors: List[bool] = []
        self._fills: List[bool] = []

        # Timestamps
        self._last_decision: Optional[datetime] = None
        self._last_event: Optional[datetime] = None
        self._decision_count = 0
        self._event_count = 0
        self._start_time = datetime.utcnow()

        # Alerts
        self._active_alerts: Dict[str, Alert] = {}
        self._alert_history: List[Alert] = []

    def process(self) -> None:
        """Check all metrics and raise alerts."""
        self._check_latency()
        self._check_error_rate()
        self._check_staleness()
        self._check_fill_rate()

    def on_message(self, message: AgentMessage) -> Optional[AgentMessage]:
        """Handle incoming messages."""
        if message.type == "health_request":
            return AgentMessage(
                type="health_response",
                payload=self.get_health_snapshot().to_dict() if hasattr(self.get_health_snapshot(), 'to_dict') else {},
            )
        return None

    def record_latency(self, latency_ms: float) -> None:
        """Record a latency measurement."""
        self._latencies.append(latency_ms)
        self._latencies = self._latencies[-self.window_size:]

    def record_decision(self) -> None:
        """Record a decision was made."""
        self._last_decision = datetime.utcnow()
        self._decision_count += 1

    def record_event(self) -> None:
        """Record an event was received."""
        self._last_event = datetime.utcnow()
        self._event_count += 1

    def record_error(self) -> None:
        """Record an error occurred."""
        self._errors.append(True)
        self._errors = self._errors[-self.window_size:]

    def record_success(self) -> None:
        """Record a successful operation."""
        self._errors.append(False)
        self._errors = self._errors[-self.window_size:]

    def record_fill(self, filled: bool) -> None:
        """Record a bet fill result."""
        self._fills.append(filled)
        self._fills = self._fills[-self.window_size:]

    def _get_latency_p95(self) -> float:
        """Get P95 latency from window."""
        if not self._latencies:
            return 0.0
        sorted_lat = sorted(self._latencies)
        idx = int(len(sorted_lat) * 0.95)
        return sorted_lat[min(idx, len(sorted_lat) - 1)]

    def _get_error_rate(self) -> float:
        """Get error rate from window."""
        if not self._errors:
            return 0.0
        return sum(self._errors) / len(self._errors)

    def _get_fill_rate(self) -> float:
        """Get fill rate from window."""
        if not self._fills:
            return 1.0
        return sum(self._fills) / len(self._fills)

    def _check_latency(self) -> None:
        """Check latency thresholds."""
        p95 = self._get_latency_p95()
        if p95 == 0:
            return

        alert_key = "latency"

        if p95 >= self.latency_crit_ms:
            self._raise_alert(Alert(
                level=AlertLevel.CRITICAL,
                source=self.agent_id,
                message=f"Latency P95 critical: {p95:.0f}ms",
                metric_name="latency_p95_ms",
                metric_value=p95,
                threshold=self.latency_crit_ms,
            ), alert_key)
        elif p95 >= self.latency_warn_ms:
            self._raise_alert(Alert(
                level=AlertLevel.WARNING,
                source=self.agent_id,
                message=f"Latency P95 elevated: {p95:.0f}ms",
                metric_name="latency_p95_ms",
                metric_value=p95,
                threshold=self.latency_warn_ms,
            ), alert_key)
        else:
            self._clear_alert(alert_key)

    def _check_error_rate(self) -> None:
        """Check error rate thresholds."""
        rate = self._get_error_rate()
        alert_key = "error_rate"

        if rate >= self.error_rate_crit:
            self._raise_alert(Alert(
                level=AlertLevel.CRITICAL,
                source=self.agent_id,
                message=f"Error rate critical: {rate:.1%}",
                metric_name="error_rate",
                metric_value=rate,
                threshold=self.error_rate_crit,
            ), alert_key)
        elif rate >= self.error_rate_warn:
            self._raise_alert(Alert(
                level=AlertLevel.WARNING,
                source=self.agent_id,
                message=f"Error rate elevated: {rate:.1%}",
                metric_name="error_rate",
                metric_value=rate,
                threshold=self.error_rate_warn,
            ), alert_key)
        else:
            self._clear_alert(alert_key)

    def _check_staleness(self) -> None:
        """Check for stale data."""
        now = datetime.utcnow()

        # Decision staleness
        if self._last_decision:
            age = (now - self._last_decision).total_seconds()
            alert_key = "decision_stale"

            if age >= self.staleness_crit_s:
                self._raise_alert(Alert(
                    level=AlertLevel.CRITICAL,
                    source=self.agent_id,
                    message=f"No decisions for {age:.0f}s",
                    metric_name="decision_age_s",
                    metric_value=age,
                    threshold=self.staleness_crit_s,
                ), alert_key)
            elif age >= self.staleness_warn_s:
                self._raise_alert(Alert(
                    level=AlertLevel.WARNING,
                    source=self.agent_id,
                    message=f"Decisions delayed: {age:.0f}s since last",
                    metric_name="decision_age_s",
                    metric_value=age,
                    threshold=self.staleness_warn_s,
                ), alert_key)
            else:
                self._clear_alert(alert_key)

        # Event staleness
        if self._last_event:
            age = (now - self._last_event).total_seconds()
            alert_key = "event_stale"

            if age >= self.staleness_crit_s:
                self._raise_alert(Alert(
                    level=AlertLevel.CRITICAL,
                    source=self.agent_id,
                    message=f"No events for {age:.0f}s",
                    metric_name="event_age_s",
                    metric_value=age,
                    threshold=self.staleness_crit_s,
                ), alert_key)
            elif age >= self.staleness_warn_s:
                self._raise_alert(Alert(
                    level=AlertLevel.WARNING,
                    source=self.agent_id,
                    message=f"Events delayed: {age:.0f}s since last",
                    metric_name="event_age_s",
                    metric_value=age,
                    threshold=self.staleness_warn_s,
                ), alert_key)
            else:
                self._clear_alert(alert_key)

    def _check_fill_rate(self) -> None:
        """Check fill rate threshold."""
        rate = self._get_fill_rate()
        alert_key = "fill_rate"

        if len(self._fills) >= 10 and rate < self.fill_rate_warn:
            self._raise_alert(Alert(
                level=AlertLevel.WARNING,
                source=self.agent_id,
                message=f"Fill rate low: {rate:.1%}",
                metric_name="fill_rate",
                metric_value=rate,
                threshold=self.fill_rate_warn,
            ), alert_key)
        else:
            self._clear_alert(alert_key)

    def _raise_alert(self, alert: Alert, key: str) -> None:
        """Raise or update an alert."""
        if key not in self._active_alerts:
            self._active_alerts[key] = alert
            self._alert_history.append(alert)
            self.logger.warning(f"ALERT: {alert.message}")

            # Broadcast alert
            self.send_message(AgentMessage(
                type="alert",
                payload=alert.to_dict(),
                priority=2 if alert.level == AlertLevel.CRITICAL else 1,
            ))

    def _clear_alert(self, key: str) -> None:
        """Clear an active alert."""
        if key in self._active_alerts:
            del self._active_alerts[key]
            self.logger.info(f"Alert cleared: {key}")

    def get_active_alerts(self) -> List[Alert]:
        """Get all active alerts."""
        return list(self._active_alerts.values())

    def get_alert_history(self, limit: int = 50) -> List[Dict]:
        """Get recent alert history."""
        return [a.to_dict() for a in self._alert_history[-limit:]]

    def get_health_snapshot(self) -> Dict:
        """Get current health snapshot."""
        now = datetime.utcnow()
        runtime = (now - self._start_time).total_seconds()
        hours = max(runtime / 3600, 1/60)  # At least 1 minute

        return {
            "timestamp": now.isoformat(),
            "latency_p95_ms": round(self._get_latency_p95(), 1),
            "error_rate": round(self._get_error_rate(), 4),
            "fill_rate": round(self._get_fill_rate(), 4),
            "decisions_per_hour": round(self._decision_count / hours, 1),
            "events_per_hour": round(self._event_count / hours, 1),
            "last_decision_age_s": (now - self._last_decision).total_seconds() if self._last_decision else None,
            "last_event_age_s": (now - self._last_event).total_seconds() if self._last_event else None,
            "active_alerts": len(self._active_alerts),
            "runtime_hours": round(hours, 2),
        }

    def get_status(self) -> Dict:
        """Get full monitor status."""
        return {
            "health": self.get_health_snapshot(),
            "alerts": [a.to_dict() for a in self._active_alerts.values()],
            "thresholds": {
                "latency_warn_ms": self.latency_warn_ms,
                "latency_crit_ms": self.latency_crit_ms,
                "error_rate_warn": self.error_rate_warn,
                "staleness_warn_s": self.staleness_warn_s,
                "fill_rate_warn": self.fill_rate_warn,
            },
        }
