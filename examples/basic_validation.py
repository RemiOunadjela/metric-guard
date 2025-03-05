"""Basic validation example: load metrics and run quality checks."""

from datetime import datetime, timedelta
from pathlib import Path

from metric_guard.registry.loader import load_metrics
from metric_guard.registry.graph import DependencyGraph
from metric_guard.rules.completeness import CompletenessRule
from metric_guard.rules.freshness import FreshnessRule
from metric_guard.rules.volume import VolumeRule
from metric_guard.audit.store import AuditStore


def main() -> None:
    # Load metric definitions
    metrics = load_metrics(Path(__file__).parent / "transparency_metrics.yaml")
    print(f"Loaded {len(metrics)} metrics\n")

    # Build dependency graph and get safe validation order
    graph = DependencyGraph(metrics)
    order = graph.topological_order()
    print(f"Validation order: {' -> '.join(order)}\n")

    # Set up audit trail
    store = AuditStore(":memory:")

    # Run validations for the content_violation_rate metric
    metric = graph.get_metric("content_violation_rate")
    print(f"Validating: {metric.display_name} (v{metric.version})")

    # Completeness check
    completeness = CompletenessRule(
        required_columns=["review_id", "decision", "review_date", "content_type"]
    )
    sample_data = {
        "review_id": ["r001", "r002", "r003", "r004", "r005"],
        "decision": ["violation", "clean", "violation", None, "clean"],
        "review_date": ["2024-06-01"] * 5,
        "content_type": ["video", "image", "text", "video", "image"],
    }
    result = completeness.validate(metric, sample_data)
    print(f"  Completeness: {result.status.value} - {result.message}")
    store.record_result(result)

    # Freshness check
    freshness = FreshnessRule()
    latest_ts = datetime.utcnow() - timedelta(hours=6)
    result = freshness.validate(metric, latest_ts)
    print(f"  Freshness:    {result.status.value} - {result.message}")
    store.record_result(result)

    # Volume check
    volume = VolumeRule(min_count=1000)
    result = volume.validate(metric, 5)
    print(f"  Volume:       {result.status.value} - {result.message}")
    store.record_result(result)

    # Print audit summary
    print(f"\nAudit summary: {store.get_summary()}")

    store.close()


if __name__ == "__main__":
    main()
