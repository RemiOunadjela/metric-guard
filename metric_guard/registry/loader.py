"""YAML-based metric definition loader."""

from __future__ import annotations

from pathlib import Path

import yaml

from metric_guard.registry.metric import MetricDefinition


def load_metrics(path: str | Path) -> list[MetricDefinition]:
    """Load metric definitions from a single YAML file.

    The file should contain a top-level ``metrics`` key with a list of
    metric objects, or a single metric object at the top level.
    """
    path = Path(path)
    with open(path) as f:
        raw = yaml.safe_load(f)

    if raw is None:
        return []

    if isinstance(raw, dict) and "metrics" in raw:
        entries = raw["metrics"]
    elif isinstance(raw, list):
        entries = raw
    elif isinstance(raw, dict):
        entries = [raw]
    else:
        raise ValueError(f"Unexpected YAML structure in {path}")

    return [MetricDefinition(**entry) for entry in entries]


def load_metrics_from_dir(
    directory: str | Path,
    pattern: str = "*.yaml",
    recursive: bool = True,
) -> list[MetricDefinition]:
    """Load all metric definitions from YAML files in a directory.

    Deduplicates by metric name, keeping the last definition seen
    (mimicking override semantics for env-specific files).
    """
    directory = Path(directory)
    if not directory.is_dir():
        raise FileNotFoundError(f"Metrics directory not found: {directory}")

    glob_method = directory.rglob if recursive else directory.glob
    seen: dict[str, MetricDefinition] = {}

    for yaml_file in sorted(glob_method(pattern)):
        for metric in load_metrics(yaml_file):
            seen[metric.name] = metric

    return list(seen.values())
