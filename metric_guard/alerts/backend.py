"""Alert backend interface and data models."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from metric_guard.registry.metric import Severity


class Alert(BaseModel):
    """An alert triggered by a validation failure."""

    alert_id: str
    metric_name: str
    rule_name: str
    severity: Severity
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    dedup_key: str = ""

    def model_post_init(self, __context: Any) -> None:
        if not self.dedup_key:
            self.dedup_key = f"{self.metric_name}:{self.rule_name}:{self.severity.value}"


class AlertBackend(ABC):
    """Interface for alert delivery backends."""

    @abstractmethod
    def send(self, alert: Alert) -> bool:
        """Deliver an alert. Returns True if successful."""
        ...

    @abstractmethod
    def test_connection(self) -> bool:
        """Verify the backend is reachable."""
        ...


class AlertRouter:
    """Route alerts to one or more backends with deduplication.

    Keeps a time-windowed set of dedup keys to avoid spamming the same
    alert during an extended outage.
    """

    def __init__(
        self,
        backends: list[AlertBackend],
        dedup_window_minutes: int = 120,
    ) -> None:
        self.backends = backends
        self.dedup_window_minutes = dedup_window_minutes
        self._seen: dict[str, datetime] = {}

    def send(self, alert: Alert) -> list[bool]:
        """Route an alert to all backends, respecting dedup window."""
        now = datetime.utcnow()

        # Prune expired entries
        self._seen = {
            k: v
            for k, v in self._seen.items()
            if (now - v).total_seconds() < self.dedup_window_minutes * 60
        }

        if alert.dedup_key in self._seen:
            return []  # suppressed

        self._seen[alert.dedup_key] = now
        return [backend.send(alert) for backend in self.backends]
