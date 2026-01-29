"""
Prometheus Metrics for Vektorr Brain.

Exposes metrics at /metrics endpoint for Prometheus scraping.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional
from collections import deque
import time
import threading


@dataclass
class MetricValue:
    """Single metric value with labels."""
    name: str
    value: float
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: Optional[float] = None


class Counter:
    """Prometheus-style counter (only increases)."""

    def __init__(self, name: str, description: str, labels: List[str] = None):
        self.name = name
        self.description = description
        self.label_names = labels or []
        self._values: Dict[tuple, float] = {}
        self._lock = threading.Lock()

    def inc(self, value: float = 1, **labels):
        """Increment counter."""
        key = tuple(labels.get(l, "") for l in self.label_names)
        with self._lock:
            self._values[key] = self._values.get(key, 0) + value

    def get(self, **labels) -> float:
        """Get current value."""
        key = tuple(labels.get(l, "") for l in self.label_names)
        return self._values.get(key, 0)

    def collect(self) -> List[MetricValue]:
        """Collect all values for export."""
        result = []
        with self._lock:
            for key, value in self._values.items():
                labels = dict(zip(self.label_names, key))
                result.append(MetricValue(self.name, value, labels))
        return result


class Gauge:
    """Prometheus-style gauge (can increase or decrease)."""

    def __init__(self, name: str, description: str, labels: List[str] = None):
        self.name = name
        self.description = description
        self.label_names = labels or []
        self._values: Dict[tuple, float] = {}
        self._lock = threading.Lock()

    def set(self, value: float, **labels):
        """Set gauge value."""
        key = tuple(labels.get(l, "") for l in self.label_names)
        with self._lock:
            self._values[key] = value

    def inc(self, value: float = 1, **labels):
        """Increment gauge."""
        key = tuple(labels.get(l, "") for l in self.label_names)
        with self._lock:
            self._values[key] = self._values.get(key, 0) + value

    def dec(self, value: float = 1, **labels):
        """Decrement gauge."""
        self.inc(-value, **labels)

    def get(self, **labels) -> float:
        """Get current value."""
        key = tuple(labels.get(l, "") for l in self.label_names)
        return self._values.get(key, 0)

    def collect(self) -> List[MetricValue]:
        """Collect all values for export."""
        result = []
        with self._lock:
            for key, value in self._values.items():
                labels = dict(zip(self.label_names, key))
                result.append(MetricValue(self.name, value, labels))
        return result


class Histogram:
    """Prometheus-style histogram for latency tracking."""

    DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

    def __init__(self, name: str, description: str, labels: List[str] = None,
                 buckets: tuple = None):
        self.name = name
        self.description = description
        self.label_names = labels or []
        self.buckets = buckets or self.DEFAULT_BUCKETS
        self._counts: Dict[tuple, Dict[float, int]] = {}
        self._sums: Dict[tuple, float] = {}
        self._totals: Dict[tuple, int] = {}
        self._lock = threading.Lock()

    def observe(self, value: float, **labels):
        """Record an observation."""
        key = tuple(labels.get(l, "") for l in self.label_names)
        with self._lock:
            if key not in self._counts:
                self._counts[key] = {b: 0 for b in self.buckets}
                self._sums[key] = 0
                self._totals[key] = 0

            for bucket in self.buckets:
                if value <= bucket:
                    self._counts[key][bucket] += 1

            self._sums[key] += value
            self._totals[key] += 1

    def collect(self) -> List[MetricValue]:
        """Collect all values for export."""
        result = []
        with self._lock:
            for key, counts in self._counts.items():
                labels = dict(zip(self.label_names, key))

                # Bucket values (cumulative)
                cumulative = 0
                for bucket in sorted(self.buckets):
                    cumulative += counts[bucket]
                    bucket_labels = {**labels, "le": str(bucket)}
                    result.append(MetricValue(f"{self.name}_bucket", cumulative, bucket_labels))

                # +Inf bucket
                inf_labels = {**labels, "le": "+Inf"}
                result.append(MetricValue(f"{self.name}_bucket", self._totals[key], inf_labels))

                # Sum and count
                result.append(MetricValue(f"{self.name}_sum", self._sums[key], labels))
                result.append(MetricValue(f"{self.name}_count", self._totals[key], labels))

        return result


class MetricsRegistry:
    """Central registry for all metrics."""

    def __init__(self):
        self._metrics: Dict[str, object] = {}
        self._lock = threading.Lock()

    def register(self, metric):
        """Register a metric."""
        with self._lock:
            self._metrics[metric.name] = metric
        return metric

    def counter(self, name: str, description: str, labels: List[str] = None) -> Counter:
        """Create and register a counter."""
        return self.register(Counter(name, description, labels))

    def gauge(self, name: str, description: str, labels: List[str] = None) -> Gauge:
        """Create and register a gauge."""
        return self.register(Gauge(name, description, labels))

    def histogram(self, name: str, description: str, labels: List[str] = None,
                  buckets: tuple = None) -> Histogram:
        """Create and register a histogram."""
        return self.register(Histogram(name, description, labels, buckets))

    def collect_all(self) -> List[MetricValue]:
        """Collect all metrics."""
        result = []
        with self._lock:
            for metric in self._metrics.values():
                result.extend(metric.collect())
        return result

    def export_prometheus(self) -> str:
        """Export metrics in Prometheus text format."""
        lines = []
        metrics = self.collect_all()

        # Group by metric name
        by_name: Dict[str, List[MetricValue]] = {}
        for m in metrics:
            base_name = m.name.replace("_bucket", "").replace("_sum", "").replace("_count", "")
            if base_name not in by_name:
                by_name[base_name] = []
            by_name[base_name].append(m)

        for name, values in by_name.items():
            if name in self._metrics:
                metric = self._metrics[name]
                metric_type = type(metric).__name__.lower()
                lines.append(f"# HELP {name} {metric.description}")
                lines.append(f"# TYPE {name} {metric_type}")

            for m in values:
                if m.labels:
                    label_str = ",".join(f'{k}="{v}"' for k, v in m.labels.items())
                    lines.append(f"{m.name}{{{label_str}}} {m.value}")
                else:
                    lines.append(f"{m.name} {m.value}")

        return "\n".join(lines) + "\n"


# Global registry
REGISTRY = MetricsRegistry()

# === Vektorr Metrics ===

# Request metrics
events_received = REGISTRY.counter(
    "vektorr_events_received_total",
    "Total events received",
    ["match_id", "event_type"]
)

odds_received = REGISTRY.counter(
    "vektorr_odds_received_total",
    "Total odds updates received",
    ["match_id", "market"]
)

decisions_made = REGISTRY.counter(
    "vektorr_decisions_total",
    "Total decisions made",
    ["reason", "can_bet"]
)

# Latency metrics
event_latency = REGISTRY.histogram(
    "vektorr_event_latency_seconds",
    "Event processing latency",
    ["event_type"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0)
)

data_latency = REGISTRY.histogram(
    "vektorr_data_latency_seconds",
    "Data arrival latency (t_recv - t_event)",
    ["source"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0)
)

# Gate metrics
gate_rejections = REGISTRY.counter(
    "vektorr_gate_rejections_total",
    "Gate rejection count",
    ["gate"]
)

# Trading metrics
bets_placed = REGISTRY.counter(
    "vektorr_bets_placed_total",
    "Total bets placed",
    ["market", "selection"]
)

bets_won = REGISTRY.counter(
    "vektorr_bets_won_total",
    "Total bets won",
    ["market"]
)

bets_lost = REGISTRY.counter(
    "vektorr_bets_lost_total",
    "Total bets lost",
    ["market"]
)

pnl_total = REGISTRY.gauge(
    "vektorr_pnl_total",
    "Total P&L"
)

bankroll_current = REGISTRY.gauge(
    "vektorr_bankroll_current",
    "Current bankroll"
)

# System metrics
active_matches = REGISTRY.gauge(
    "vektorr_active_matches",
    "Number of active matches being tracked"
)

kill_switch_active = REGISTRY.gauge(
    "vektorr_kill_switch_active",
    "Kill switch status (1=frozen, 0=running)"
)

staged_rollout_stage = REGISTRY.gauge(
    "vektorr_staged_rollout_stage",
    "Current rollout stage (0=paper, 1=micro, 2=small, 3=full)"
)

# Error metrics
errors_total = REGISTRY.counter(
    "vektorr_errors_total",
    "Total errors",
    ["component", "error_type"]
)

# Provider metrics
provider_requests = REGISTRY.counter(
    "vektorr_provider_requests_total",
    "Provider API requests",
    ["provider", "endpoint"]
)

provider_errors = REGISTRY.counter(
    "vektorr_provider_errors_total",
    "Provider API errors",
    ["provider", "error_type"]
)

provider_latency = REGISTRY.histogram(
    "vektorr_provider_latency_seconds",
    "Provider API latency",
    ["provider"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0)
)


def get_metrics_text() -> str:
    """Get metrics in Prometheus text format."""
    return REGISTRY.export_prometheus()
