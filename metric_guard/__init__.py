"""metric-guard: Automated data quality for compliance metrics."""

__version__ = "0.1.0"

from metric_guard.registry.graph import DependencyGraph
from metric_guard.registry.loader import load_metrics, load_metrics_from_dir
from metric_guard.registry.metric import MetricDefinition, Severity, UpdateFrequency

__all__ = [
    "MetricDefinition",
    "Severity",
    "UpdateFrequency",
    "load_metrics",
    "load_metrics_from_dir",
    "DependencyGraph",
]
