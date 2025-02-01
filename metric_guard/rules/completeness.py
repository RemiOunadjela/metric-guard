"""Completeness validation: detect missing or null values in required fields."""

from __future__ import annotations

from typing import Any

from metric_guard.registry.metric import MetricDefinition, Severity
from metric_guard.rules.base import RuleStatus, ValidationResult, ValidationRule


class CompletenessRule(ValidationRule):
    """Check that required columns contain no nulls.

    Parameters
    ----------
    required_columns : list[str]
        Column names that must not contain null/None values.
    max_null_fraction : float
        Acceptable fraction of nulls (0.0 = no nulls allowed, 0.05 = up to 5%).
    """

    name = "completeness"
    default_severity = Severity.ERROR

    def __init__(
        self,
        required_columns: list[str] | None = None,
        max_null_fraction: float = 0.0,
    ) -> None:
        self.required_columns = required_columns or []
        self.max_null_fraction = max_null_fraction

    def validate(
        self,
        metric: MetricDefinition,
        data: dict[str, list[Any]],
        **kwargs: Any,
    ) -> ValidationResult:
        """Validate completeness of columnar data.

        Args:
            data: dict mapping column names to lists of values.
        """
        if not data:
            return self._result(
                metric, RuleStatus.FAILED, "No data provided for completeness check"
            )

        columns_to_check = self.required_columns or list(data.keys())
        failures: dict[str, float] = {}

        for col in columns_to_check:
            if col not in data:
                failures[col] = 1.0
                continue
            values = data[col]
            if not values:
                failures[col] = 1.0
                continue
            null_count = sum(1 for v in values if v is None)
            null_frac = null_count / len(values)
            if null_frac > self.max_null_fraction:
                failures[col] = round(null_frac, 4)

        if failures:
            worst = max(failures.values())
            return self._result(
                metric,
                RuleStatus.FAILED,
                f"{len(failures)} column(s) exceed null threshold: "
                f"{', '.join(failures.keys())}",
                details={"null_fractions": failures, "threshold": self.max_null_fraction},
                severity=Severity.CRITICAL if worst > 0.5 else self.default_severity,
            )

        return self._result(
            metric,
            RuleStatus.PASSED,
            f"All {len(columns_to_check)} columns pass completeness check",
        )
