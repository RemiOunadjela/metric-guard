"""Consistency validation: cross-metric coherence checks."""

from __future__ import annotations

from typing import Any

from metric_guard.registry.metric import MetricDefinition, Severity
from metric_guard.rules.base import RuleStatus, ValidationResult, ValidationRule


class ConsistencyRule(ValidationRule):
    """Verify logical consistency between related metrics.

    Classic example: proactive detection count + reactive detection count
    should roughly equal total detection count. When they diverge,
    something upstream is double-counting or dropping records.
    """

    name = "consistency"
    default_severity = Severity.ERROR

    def __init__(
        self,
        relation: str = "sum",
        tolerance: float = 0.01,
    ) -> None:
        """
        Args:
            relation: One of 'sum' (parts should sum to total),
                      'ratio' (ratio should be within bounds),
                      'equality' (values should match within tolerance).
            tolerance: Acceptable relative deviation.
        """
        if relation not in ("sum", "ratio", "equality"):
            raise ValueError(f"Unsupported relation: {relation}")
        self.relation = relation
        self.tolerance = tolerance

    def validate(
        self,
        metric: MetricDefinition,
        data: Any,
        **kwargs: Any,
    ) -> ValidationResult:
        """Validate cross-metric consistency.

        Args:
            data: For 'sum': dict with ``parts`` (list of floats) and ``total`` (float).
                  For 'ratio': dict with ``numerator``, ``denominator``, ``expected_ratio``.
                  For 'equality': dict with ``values`` (list of floats that should be equal).
        """
        if not isinstance(data, dict):
            return self._result(
                metric, RuleStatus.SKIPPED, "Expected dict input for consistency check"
            )

        if self.relation == "sum":
            return self._check_sum(metric, data)
        elif self.relation == "ratio":
            return self._check_ratio(metric, data)
        else:
            return self._check_equality(metric, data)

    def _check_sum(self, metric: MetricDefinition, data: dict) -> ValidationResult:
        parts = data.get("parts", [])
        total = data.get("total")
        if total is None or not parts:
            return self._result(metric, RuleStatus.SKIPPED, "Missing 'parts' or 'total'")

        computed_sum = sum(parts)
        if total == 0:
            deviation = abs(computed_sum)
        else:
            deviation = abs(computed_sum - total) / abs(total)

        details = {
            "parts_sum": computed_sum,
            "expected_total": total,
            "deviation": round(deviation, 6),
            "tolerance": self.tolerance,
        }

        if deviation > self.tolerance:
            return self._result(
                metric,
                RuleStatus.FAILED,
                f"Sum of parts ({computed_sum}) deviates from total ({total}) "
                f"by {deviation:.2%} (tolerance: {self.tolerance:.2%})",
                details=details,
            )

        return self._result(
            metric, RuleStatus.PASSED, "Sum consistency check passed", details=details
        )

    def _check_ratio(self, metric: MetricDefinition, data: dict) -> ValidationResult:
        num = data.get("numerator")
        den = data.get("denominator")
        expected = data.get("expected_ratio")

        if num is None or den is None or expected is None:
            return self._result(metric, RuleStatus.SKIPPED, "Missing ratio components")

        if den == 0:
            return self._result(metric, RuleStatus.FAILED, "Denominator is zero")

        actual_ratio = num / den
        deviation = abs(actual_ratio - expected)

        details = {
            "actual_ratio": round(actual_ratio, 6),
            "expected_ratio": expected,
            "deviation": round(deviation, 6),
        }

        if deviation > self.tolerance:
            return self._result(
                metric,
                RuleStatus.FAILED,
                f"Ratio {actual_ratio:.4f} deviates from expected {expected} "
                f"by {deviation:.4f}",
                details=details,
            )

        return self._result(
            metric, RuleStatus.PASSED, "Ratio consistency check passed", details=details
        )

    def _check_equality(self, metric: MetricDefinition, data: dict) -> ValidationResult:
        values = data.get("values", [])
        if len(values) < 2:
            return self._result(metric, RuleStatus.SKIPPED, "Need at least 2 values to compare")

        reference = values[0]
        mismatches: list[dict] = []
        for i, v in enumerate(values[1:], 1):
            if reference == 0:
                dev = abs(v)
            else:
                dev = abs(v - reference) / abs(reference)
            if dev > self.tolerance:
                mismatches.append({"index": i, "value": v, "deviation": round(dev, 6)})

        if mismatches:
            return self._result(
                metric,
                RuleStatus.FAILED,
                f"{len(mismatches)} value(s) deviate beyond tolerance",
                details={"reference": reference, "mismatches": mismatches},
            )

        return self._result(metric, RuleStatus.PASSED, "Equality consistency check passed")
