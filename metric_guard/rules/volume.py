"""Volume validation: row count and value bounds checking."""

from __future__ import annotations

from typing import Any

from metric_guard.registry.metric import MetricDefinition, Severity
from metric_guard.rules.base import RuleStatus, ValidationResult, ValidationRule


class VolumeRule(ValidationRule):
    """Check that data volume (row counts or aggregate values) falls within expected bounds.

    Catching a 90% drop in content moderation actions at 2am is much better
    than discovering it in the weekly review.
    """

    name = "volume"
    default_severity = Severity.ERROR

    def __init__(
        self,
        min_count: int | None = None,
        max_count: int | None = None,
        min_value: float | None = None,
        max_value: float | None = None,
    ) -> None:
        self.min_count = min_count
        self.max_count = max_count
        self.min_value = min_value
        self.max_value = max_value

    def validate(
        self,
        metric: MetricDefinition,
        data: Any,
        **kwargs: Any,
    ) -> ValidationResult:
        """Validate data volume.

        Args:
            data: Either an int/float (row count or metric value),
                  or a dict with ``count`` and/or ``value`` keys.
        """
        count: int | None = None
        value: float | None = None

        if isinstance(data, int):
            count = data
        elif isinstance(data, float):
            value = data
        elif isinstance(data, dict):
            count = data.get("count")
            value = data.get("value")
        else:
            return self._result(
                metric, RuleStatus.SKIPPED, "Unsupported data format for volume check"
            )

        violations: list[str] = []
        details: dict[str, Any] = {}

        if count is not None:
            details["count"] = count
            if self.min_count is not None and count < self.min_count:
                violations.append(f"count {count} below minimum {self.min_count}")
            if self.max_count is not None and count > self.max_count:
                violations.append(f"count {count} above maximum {self.max_count}")

        if value is not None:
            details["value"] = value
            if self.min_value is not None and value < self.min_value:
                violations.append(f"value {value:.4f} below minimum {self.min_value}")
            if self.max_value is not None and value > self.max_value:
                violations.append(f"value {value:.4f} above maximum {self.max_value}")

        if violations:
            return self._result(
                metric,
                RuleStatus.FAILED,
                "; ".join(violations),
                details=details,
            )

        return self._result(metric, RuleStatus.PASSED, "Volume within bounds", details=details)


class MonotonicityRule(ValidationRule):
    """Check that a sequence of values is monotonically non-decreasing.

    Useful for cumulative counters like total actions taken, total appeals processed.
    A decrease usually indicates a data pipeline reset or corruption.
    """

    name = "monotonicity"
    default_severity = Severity.CRITICAL

    def __init__(self, strict: bool = False) -> None:
        self.strict = strict

    def validate(
        self,
        metric: MetricDefinition,
        data: Any,
        **kwargs: Any,
    ) -> ValidationResult:
        """Validate monotonicity of a value sequence.

        Args:
            data: A list of numeric values in chronological order.
        """
        if not isinstance(data, (list, tuple)) or len(data) < 2:
            return self._result(
                metric, RuleStatus.SKIPPED, "Need at least 2 data points for monotonicity check"
            )

        violations: list[dict[str, Any]] = []
        for i in range(1, len(data)):
            if self.strict and data[i] <= data[i - 1]:
                violations.append({"index": i, "prev": data[i - 1], "curr": data[i]})
            elif not self.strict and data[i] < data[i - 1]:
                violations.append({"index": i, "prev": data[i - 1], "curr": data[i]})

        if violations:
            return self._result(
                metric,
                RuleStatus.FAILED,
                f"{len(violations)} monotonicity violation(s) detected",
                details={"violations": violations[:10]},  # cap detail size
            )

        return self._result(metric, RuleStatus.PASSED, "Monotonicity check passed")


class RangeRule(ValidationRule):
    """Validate that all values in a series fall within acceptable bounds.

    Think: appeal overturn rates should never exceed 100% or go negative.
    """

    name = "range"
    default_severity = Severity.ERROR

    def __init__(
        self,
        min_value: float | None = None,
        max_value: float | None = None,
    ) -> None:
        self.min_value = min_value
        self.max_value = max_value

    def validate(
        self,
        metric: MetricDefinition,
        data: Any,
        **kwargs: Any,
    ) -> ValidationResult:
        if not isinstance(data, (list, tuple)):
            data = [data]

        out_of_range: list[dict[str, Any]] = []
        for i, val in enumerate(data):
            if not isinstance(val, (int, float)):
                continue
            if self.min_value is not None and val < self.min_value:
                out_of_range.append({"index": i, "value": val, "bound": "min"})
            if self.max_value is not None and val > self.max_value:
                out_of_range.append({"index": i, "value": val, "bound": "max"})

        if out_of_range:
            return self._result(
                metric,
                RuleStatus.FAILED,
                f"{len(out_of_range)} value(s) outside [{self.min_value}, {self.max_value}]",
                details={"violations": out_of_range[:20]},
            )

        return self._result(metric, RuleStatus.PASSED, "All values within range")
