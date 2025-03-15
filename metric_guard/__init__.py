"""metric-guard: Automated data quality for compliance metrics."""

__version__ = "0.4.1"

from metric_guard.registry.graph import DependencyGraph
from metric_guard.registry.loader import load_metrics, load_metrics_from_dir
from metric_guard.registry.metric import MetricDefinition, Severity, UpdateFrequency
from metric_guard.rules.base import ValidationResult, ValidationRule
from metric_guard.rules.custom import rule

__all__ = [
    "MetricDefinition",
    "Severity",
    "UpdateFrequency",
    "load_metrics",
    "load_metrics_from_dir",
    "DependencyGraph",
    "ValidationResult",
    "ValidationRule",
    "rule",
]
