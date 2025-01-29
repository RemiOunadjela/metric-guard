"""Base classes for validation rules."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from metric_guard.registry.metric import MetricDefinition, Severity


class RuleStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ValidationResult(BaseModel):
    """Outcome of a single validation rule execution."""

    rule_name: str
    metric_name: str
    status: RuleStatus
    severity: Severity = Severity.ERROR
    message: str = ""
    details: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    @property
    def passed(self) -> bool:
        return self.status == RuleStatus.PASSED


class ValidationRule(ABC):
    """Base class for all validation rules.

    Subclasses implement ``validate`` which receives the metric definition
    and whatever data context is relevant (a DataFrame-like dict of columns,
    a scalar value, etc.) and returns a ``ValidationResult``.
    """

    name: str = "base"
    default_severity: Severity = Severity.ERROR

    @abstractmethod
    def validate(
        self,
        metric: MetricDefinition,
        data: Any,
        **kwargs: Any,
    ) -> ValidationResult:
        ...

    def _result(
        self,
        metric: MetricDefinition,
        status: RuleStatus,
        message: str = "",
        details: dict[str, Any] | None = None,
        severity: Severity | None = None,
    ) -> ValidationResult:
        return ValidationResult(
            rule_name=self.name,
            metric_name=metric.name,
            status=status,
            severity=severity or self.default_severity,
            message=message,
            details=details or {},
        )
