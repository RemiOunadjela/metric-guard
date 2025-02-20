"""Escalation rules based on alert severity and duration."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from metric_guard.alerts.backend import Alert, AlertBackend
from metric_guard.registry.metric import Severity


class EscalationRule:
    """Defines when an alert should escalate to a different backend or severity."""

    def __init__(
        self,
        min_severity: Severity,
        after_minutes: int,
        escalate_to: AlertBackend,
        escalated_severity: Severity | None = None,
    ) -> None:
        self.min_severity = min_severity
        self.after_minutes = after_minutes
        self.escalate_to = escalate_to
        self.escalated_severity = escalated_severity


class EscalationManager:
    """Track open alerts and apply escalation rules.

    If a critical alert stays unresolved for 30 minutes, page the on-call.
    If an error-level alert persists for 2 hours, promote to critical.
    That kind of thing.
    """

    def __init__(self, rules: list[EscalationRule] | None = None) -> None:
        self.rules = rules or []
        self._open_alerts: dict[str, dict[str, Any]] = {}

    def track(self, alert: Alert) -> None:
        """Record an alert as open."""
        self._open_alerts[alert.dedup_key] = {
            "alert": alert,
            "first_seen": datetime.utcnow(),
            "escalated_at": set(),
        }

    def resolve(self, dedup_key: str) -> None:
        """Mark an alert as resolved."""
        self._open_alerts.pop(dedup_key, None)

    def check_escalations(self) -> list[Alert]:
        """Evaluate all open alerts against escalation rules.

        Returns a list of escalated alerts that were sent.
        """
        now = datetime.utcnow()
        escalated: list[Alert] = []

        for dedup_key, entry in list(self._open_alerts.items()):
            alert: Alert = entry["alert"]
            age = now - entry["first_seen"]

            for i, rule in enumerate(self.rules):
                rule_id = f"rule_{i}"
                if rule_id in entry["escalated_at"]:
                    continue

                severity_rank = {Severity.WARNING: 0, Severity.ERROR: 1, Severity.CRITICAL: 2}
                if severity_rank.get(alert.severity, 0) < severity_rank.get(
                    rule.min_severity, 0
                ):
                    continue

                if age >= timedelta(minutes=rule.after_minutes):
                    escalated_alert = alert.model_copy(
                        update={
                            "severity": rule.escalated_severity or alert.severity,
                            "message": f"[ESCALATED after {rule.after_minutes}m] {alert.message}",
                        }
                    )
                    rule.escalate_to.send(escalated_alert)
                    entry["escalated_at"].add(rule_id)
                    escalated.append(escalated_alert)

        return escalated

    @property
    def open_alert_count(self) -> int:
        return len(self._open_alerts)
