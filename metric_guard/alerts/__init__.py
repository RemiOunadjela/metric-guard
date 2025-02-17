"""Alerting backends and escalation logic."""

from metric_guard.alerts.backend import Alert, AlertBackend
from metric_guard.alerts.console import ConsoleAlertBackend
from metric_guard.alerts.slack import SlackAlertBackend

__all__ = [
    "AlertBackend",
    "Alert",
    "ConsoleAlertBackend",
    "SlackAlertBackend",
]
