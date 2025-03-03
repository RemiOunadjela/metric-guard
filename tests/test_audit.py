"""Tests for audit trail storage and export."""

import json
from datetime import datetime

import pytest

from metric_guard.audit.export import AuditExporter
from metric_guard.audit.store import AuditStore
from metric_guard.registry.metric import Severity
from metric_guard.rules.base import RuleStatus, ValidationResult


@pytest.fixture
def store() -> AuditStore:
    """In-memory SQLite store for testing."""
    s = AuditStore(":memory:")
    yield s
    s.close()


@pytest.fixture
def populated_store(store: AuditStore) -> AuditStore:
    """Store with some pre-loaded validation results."""
    results = [
        ValidationResult(
            rule_name="freshness",
            metric_name="content_violation_rate",
            status=RuleStatus.PASSED,
            severity=Severity.ERROR,
            message="Data is 6h old",
        ),
        ValidationResult(
            rule_name="completeness",
            metric_name="content_violation_rate",
            status=RuleStatus.FAILED,
            severity=Severity.CRITICAL,
            message="2 columns have nulls",
            details={"null_fractions": {"col_a": 0.1}},
        ),
        ValidationResult(
            rule_name="freshness",
            metric_name="appeal_overturn_rate",
            status=RuleStatus.FAILED,
            severity=Severity.ERROR,
            message="Data is 30h old",
        ),
    ]
    store.record_batch(results)
    return store


class TestAuditStore:
    def test_record_and_query(self, store: AuditStore) -> None:
        result = ValidationResult(
            rule_name="freshness",
            metric_name="test_metric",
            status=RuleStatus.PASSED,
            severity=Severity.ERROR,
            message="fresh",
        )
        run_id = store.record_result(result)
        assert run_id

        runs = store.query_runs(metric_name="test_metric")
        assert len(runs) == 1
        assert runs[0]["status"] == "passed"

    def test_record_batch(self, populated_store: AuditStore) -> None:
        runs = populated_store.query_runs()
        assert len(runs) == 3

    def test_query_by_status(self, populated_store: AuditStore) -> None:
        failed = populated_store.query_runs(status="failed")
        assert len(failed) == 2

    def test_query_by_metric(self, populated_store: AuditStore) -> None:
        runs = populated_store.query_runs(metric_name="content_violation_rate")
        assert len(runs) == 2

    def test_record_change(self, store: AuditStore) -> None:
        change_id = store.record_change(
            metric_name="test_metric",
            field_name="sla_hours",
            old_value=24,
            new_value=12,
            changed_by="remi",
        )
        assert change_id
        changes = store.query_changes(metric_name="test_metric")
        assert len(changes) == 1
        assert changes[0]["field_name"] == "sla_hours"

    def test_summary(self, populated_store: AuditStore) -> None:
        summary = populated_store.get_summary()
        assert summary["total_runs"] == 3
        assert summary["by_status"]["passed"] == 1
        assert summary["by_status"]["failed"] == 2
        assert "critical" in summary["failures_by_severity"]

    def test_date_range_query(self, store: AuditStore) -> None:
        old = ValidationResult(
            rule_name="test",
            metric_name="m1",
            status=RuleStatus.PASSED,
            severity=Severity.ERROR,
            message="old",
            timestamp=datetime(2024, 1, 1),
        )
        new = ValidationResult(
            rule_name="test",
            metric_name="m1",
            status=RuleStatus.FAILED,
            severity=Severity.ERROR,
            message="new",
            timestamp=datetime(2024, 6, 15),
        )
        store.record_result(old)
        store.record_result(new)

        runs = store.query_runs(
            from_date=datetime(2024, 6, 1),
            to_date=datetime(2024, 7, 1),
        )
        assert len(runs) == 1
        assert runs[0]["message"] == "new"


class TestAuditExporter:
    def test_export_csv(self, populated_store: AuditStore) -> None:
        exporter = AuditExporter(populated_store)
        csv_output = exporter.export_csv()
        assert csv_output
        lines = csv_output.strip().split("\n")
        assert len(lines) == 4  # header + 3 rows
        assert "metric_name" in lines[0]

    def test_export_json(self, populated_store: AuditStore) -> None:
        exporter = AuditExporter(populated_store)
        json_output = exporter.export_json()
        data = json.loads(json_output)
        assert "validation_runs" in data
        assert "summary" in data
        assert len(data["validation_runs"]) == 3

    def test_export_json_with_changes(self, populated_store: AuditStore) -> None:
        populated_store.record_change("test", "sla", 24, 12)
        exporter = AuditExporter(populated_store)
        data = json.loads(exporter.export_json(include_changes=True))
        assert "metric_changes" in data
        assert len(data["metric_changes"]) == 1

    def test_empty_export(self, store: AuditStore) -> None:
        exporter = AuditExporter(store)
        assert exporter.export_csv() == ""

    def test_summary_report(self, populated_store: AuditStore) -> None:
        exporter = AuditExporter(populated_store)
        report = exporter.generate_summary_report()
        assert "overall" in report
        assert "metric_failures" in report
        assert report["metric_failures"]["content_violation_rate"] == 1
