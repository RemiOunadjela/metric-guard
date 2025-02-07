"""Custom rule support via decorators."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from metric_guard.registry.metric import MetricDefinition, Severity
from metric_guard.rules.base import RuleStatus, ValidationResult, ValidationRule


class CustomRule(ValidationRule):
    """A validation rule created from a decorated function.

    This lets teams define one-off business rules without creating
    a full class -- useful for metric-specific invariants that don't
    generalize well.
    """

    def __init__(
        self,
        func: Callable[..., bool | tuple[bool, str]],
        name: str,
        severity: Severity = Severity.ERROR,
    ) -> None:
        self._func = func
        self.name = name
        self.default_severity = severity

    def validate(
        self,
        metric: MetricDefinition,
        data: Any,
        **kwargs: Any,
    ) -> ValidationResult:
        try:
            result = self._func(metric, data, **kwargs)
        except Exception as exc:
            return self._result(
                metric,
                RuleStatus.FAILED,
                f"Custom rule raised an exception: {exc}",
                details={"exception_type": type(exc).__name__, "exception": str(exc)},
            )

        if isinstance(result, tuple):
            passed, message = result
        elif isinstance(result, bool):
            passed = result
            message = "Custom rule passed" if passed else "Custom rule failed"
        else:
            return self._result(
                metric,
                RuleStatus.FAILED,
                f"Custom rule returned unexpected type: {type(result).__name__}",
            )

        return self._result(
            metric,
            RuleStatus.PASSED if passed else RuleStatus.FAILED,
            message,
        )


def rule(
    name: str | None = None,
    severity: Severity = Severity.ERROR,
) -> Callable:
    """Decorator to create a custom validation rule from a function.

    Usage::

        @rule(name="positive_rate")
        def check_positive_rate(metric, data):
            rate = data["positives"] / data["total"]
            if rate < 0 or rate > 1:
                return False, f"Invalid rate: {rate}"
            return True, f"Rate {rate:.2%} is valid"
    """

    def decorator(func: Callable) -> CustomRule:
        rule_name = name or func.__name__
        return CustomRule(func=func, name=rule_name, severity=severity)

    return decorator
