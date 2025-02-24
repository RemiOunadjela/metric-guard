"""Global configuration for metric-guard."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

_DEFAULT_CONFIG_NAME = "metric_guard.yaml"


class AlertConfig(BaseModel):
    backend: str = "console"
    slack_webhook_url: str | None = None
    pagerduty_routing_key: str | None = None
    suppression_window_minutes: int = 60
    dedup_key_ttl_minutes: int = 120


class AuditConfig(BaseModel):
    db_path: str = ".metric_guard/audit.db"
    retention_days: int = 365


class PulseConfig(BaseModel):
    baseline_window_days: int = 30
    z_score_threshold: float = 3.0
    iqr_multiplier: float = 1.5


class MetricGuardConfig(BaseModel):
    metrics_dir: str = "metrics/"
    environment: str = "development"
    alerts: AlertConfig = Field(default_factory=AlertConfig)
    audit: AuditConfig = Field(default_factory=AuditConfig)
    pulse: PulseConfig = Field(default_factory=PulseConfig)
    extra: dict[str, Any] = Field(default_factory=dict)


def load_config(config_path: str | Path | None = None) -> MetricGuardConfig:
    """Load configuration from YAML file or environment.

    Resolution order:
    1. Explicit path argument
    2. METRIC_GUARD_CONFIG environment variable
    3. metric_guard.yaml in current directory
    4. Default values
    """
    if config_path is None:
        config_path = os.environ.get("METRIC_GUARD_CONFIG", _DEFAULT_CONFIG_NAME)

    path = Path(config_path)
    if path.exists():
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
        return MetricGuardConfig(**raw)

    return MetricGuardConfig()
