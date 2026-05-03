"""YAML-based metric definition loader."""

from __future__ import annotations

from pathlib import Path

import jsonschema
import yaml

from metric_guard.registry.metric import MetricDefinition
from metric_guard.registry.schema import METRIC_SCHEMA

_validator = jsonschema.Draft7Validator(METRIC_SCHEMA)


def _validate_entries(entries: list, path: Path) -> None:
    """Raise ValueError with actionable details if any metric entry fails schema validation."""
    all_errors: list[str] = []
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            all_errors.append(
                f"  metric [index {i}]: expected a mapping, got {type(entry).__name__}"
            )
            continue
        metric_name = entry.get("name", f"[index {i}]")
        for error in _validator.iter_errors(entry):
            loc = " > ".join(str(p) for p in error.absolute_path) or "root"
            all_errors.append(f"  '{metric_name}' > {loc}: {error.message}")
    if all_errors:
        detail = "\n".join(all_errors[:10])
        raise ValueError(f"Schema validation failed for {path}:\n{detail}")


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
        if not isinstance(raw["metrics"], list):
            raise ValueError(f"'metrics' key must contain a list in {path}")
        entries = raw["metrics"]
    elif isinstance(raw, list):
        entries = raw
    elif isinstance(raw, dict):
        entries = [raw]
    else:
        raise ValueError(f"Unexpected YAML structure in {path}")

    _validate_entries(entries, path)
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
