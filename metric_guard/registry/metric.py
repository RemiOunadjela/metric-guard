"""Core metric definition model."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Severity(str, Enum):
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class UpdateFrequency(str, Enum):
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


class ValidationRuleSpec(BaseModel):
    """Declarative rule specification attached to a metric definition."""

    type: str
    params: dict[str, Any] = Field(default_factory=dict)
    severity: Severity = Severity.ERROR


class MetricDefinition(BaseModel):
    """A compliance metric with full lineage and validation metadata.

    Every field maps directly to what regulators and internal audit teams
    need: who owns it, what it measures, how fresh it should be, and what
    constitutes a data quality failure.
    """

    name: str
    display_name: str = ""
    owner: str = ""
    business_definition: str = ""
    sql_reference: str = ""
    update_frequency: UpdateFrequency = UpdateFrequency.DAILY
    sla_hours: float = 24.0
    tags: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    version: str = "1.0.0"
    created_at: datetime | None = None
    updated_at: datetime | None = None
    rules: list[ValidationRuleSpec] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, MetricDefinition):
            return self.name == other.name
        return NotImplemented

    @property
    def qualified_name(self) -> str:
        return f"{self.name}@{self.version}"
