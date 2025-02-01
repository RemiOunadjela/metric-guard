"""Freshness validation: verify data recency against SLA."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from metric_guard.registry.metric import MetricDefinition, Severity
from metric_guard.rules.base import RuleStatus, ValidationResult, ValidationRule


class FreshnessRule(ValidationRule):
    """Verify that the most recent data point is within the expected recency window.

    In compliance reporting, stale data is often worse than missing data --
    you end up filing reports with numbers that look right but are days old.
    """

    name = "freshness"
    default_severity = Severity.ERROR

    def __init__(self, max_staleness_hours: float | None = None) -> None:
        self._max_staleness_hours = max_staleness_hours

    def validate(
        self,
        metric: MetricDefinition,
        data: Any,
        **kwargs: Any,
    ) -> ValidationResult:
        """Validate data freshness.

        Args:
            data: Either a ``datetime`` representing the latest data timestamp,
                  or a dict with a ``latest_timestamp`` key.
        """
        now = kwargs.get("reference_time", datetime.utcnow())
        max_hours = self._max_staleness_hours or metric.sla_hours

        if isinstance(data, datetime):
            latest = data
        elif isinstance(data, dict) and "latest_timestamp" in data:
            ts = data["latest_timestamp"]
            latest = ts if isinstance(ts, datetime) else datetime.fromisoformat(str(ts))
        else:
            return self._result(
                metric,
                RuleStatus.SKIPPED,
                "No timestamp data provided for freshness check",
            )

        age = now - latest
        age_hours = age.total_seconds() / 3600
        threshold = timedelta(hours=max_hours)

        if age > threshold:
            return self._result(
                metric,
                RuleStatus.FAILED,
                f"Data is {age_hours:.1f}h old, exceeds {max_hours}h SLA",
                details={
                    "age_hours": round(age_hours, 2),
                    "sla_hours": max_hours,
                    "latest_timestamp": latest.isoformat(),
                },
                severity=Severity.CRITICAL if age_hours > max_hours * 2 else self.default_severity,
            )

        return self._result(
            metric,
            RuleStatus.PASSED,
            f"Data is {age_hours:.1f}h old, within {max_hours}h SLA",
            details={"age_hours": round(age_hours, 2), "sla_hours": max_hours},
        )
