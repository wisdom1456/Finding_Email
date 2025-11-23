"""Metrics collection for observability."""

from __future__ import annotations

import json
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional


@dataclass
class Metric:
    """Metric data point."""

    name: str
    value: float
    timestamp: datetime
    tags: Dict[str, str] = field(default_factory=dict)
    metric_type: str = "gauge"  # gauge, counter, histogram, timer


class MetricsCollector:
    """Collect and export metrics."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """Singleton pattern for metrics collector."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize metrics collector."""
        if self._initialized:
            return

        self.metrics: List[Metric] = []
        self.counters: Dict[str, int] = defaultdict(int)
        self.timers: Dict[str, List[float]] = defaultdict(list)
        self.gauges: Dict[str, float] = {}
        self._initialized = True

        # Start background thread for periodic export
        self._start_exporter()

    @classmethod
    def record_counter(cls, name: str, value: int = 1, tags: Optional[Dict] = None):
        """Record counter metric."""
        instance = cls()
        instance.counters[name] += value

        metric = Metric(
            name=name, value=value, timestamp=datetime.utcnow(), tags=tags or {}, metric_type="counter"
        )
        instance.metrics.append(metric)

    @classmethod
    def record_timing(cls, name: str, duration: float, tags: Optional[Dict] = None):
        """Record timing metric."""
        instance = cls()
        instance.timers[name].append(duration)

        # Keep only last 1000 measurements
        if len(instance.timers[name]) > 1000:
            instance.timers[name] = instance.timers[name][-1000:]

        metric = Metric(
            name=f"{name}.duration",
            value=duration * 1000,  # Convert to milliseconds
            timestamp=datetime.utcnow(),
            tags=tags or {},
            metric_type="timer",
        )
        instance.metrics.append(metric)

    @classmethod
    def record_gauge(cls, name: str, value: float, tags: Optional[Dict] = None):
        """Record gauge metric."""
        instance = cls()
        instance.gauges[name] = value

        metric = Metric(
            name=name, value=value, timestamp=datetime.utcnow(), tags=tags or {}, metric_type="gauge"
        )
        instance.metrics.append(metric)

    @classmethod
    def record_error(cls, operation: str, tags: Optional[Dict] = None):
        """Record error occurrence."""
        cls.record_counter(f"{operation}.errors", 1, tags)

    def _start_exporter(self):
        """Start background metrics exporter."""

        def export_metrics():
            while True:
                time.sleep(60)  # Export every minute
                self._export_metrics()

        thread = threading.Thread(target=export_metrics, daemon=True)
        thread.start()

    def _export_metrics(self):
        """Export metrics to monitoring system."""
        # Calculate aggregates
        stats = {
            "timestamp": datetime.utcnow().isoformat(),
            "counters": dict(self.counters),
            "gauges": dict(self.gauges),
            "timers": {},
        }

        # Calculate timer statistics
        for name, values in self.timers.items():
            if values:
                stats["timers"][name] = {
                    "count": len(values),
                    "min": min(values) * 1000,
                    "max": max(values) * 1000,
                    "avg": (sum(values) / len(values)) * 1000,
                    "p50": self._percentile(values, 50) * 1000,
                    "p95": self._percentile(values, 95) * 1000,
                    "p99": self._percentile(values, 99) * 1000,
                }

        # Export to file (can be replaced with external service)
        with open("logs/metrics.json", "a") as f:
            f.write(json.dumps(stats) + "\n")

        # Clear old metrics (keep last hour)
        cutoff = datetime.utcnow() - timedelta(hours=1)
        self.metrics = [m for m in self.metrics if m.timestamp > cutoff]

    def _percentile(self, values: List[float], percentile: float) -> float:
        """Calculate percentile of values."""
        if not values:
            return 0

        sorted_values = sorted(values)
        index = int(len(sorted_values) * (percentile / 100))
        return sorted_values[min(index, len(sorted_values) - 1)]
