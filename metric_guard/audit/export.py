"""Export audit reports for regulatory review."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Any

from metric_guard.audit.store import AuditStore


class AuditExporter:
    """Generate audit reports from the validation history.

    Supports CSV and JSON export. PDF generation requires an external
    tool (weasyprint or similar) -- we generate the structured data
    and leave rendering to the caller.
    """

    def __init__(self, store: AuditStore) -> None:
        self.store = store

    def export_csv(
        self,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        metric_name: str | None = None,
    ) -> str:
        """Export validation runs as CSV."""
        runs = self.store.query_runs(
            metric_name=metric_name,
            from_date=from_date,
            to_date=to_date,
            limit=100_000,
        )

        if not runs:
            return ""

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=list(runs[0].keys()))
        writer.writeheader()
        writer.writerows(runs)
        return output.getvalue()

    def export_json(
        self,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        metric_name: str | None = None,
        include_changes: bool = True,
    ) -> str:
        """Export validation runs and changes as JSON."""
        runs = self.store.query_runs(
            metric_name=metric_name,
            from_date=from_date,
            to_date=to_date,
            limit=100_000,
        )

        report: dict[str, Any] = {
            "report_generated_at": datetime.utcnow().isoformat(),
            "period": {
                "from": from_date.isoformat() if from_date else None,
                "to": to_date.isoformat() if to_date else None,
            },
            "summary": self.store.get_summary(from_date=from_date, to_date=to_date),
            "validation_runs": runs,
        }

        if include_changes:
            report["metric_changes"] = self.store.query_changes(
                metric_name=metric_name,
                from_date=from_date,
                to_date=to_date,
            )

        return json.dumps(report, indent=2, default=str)

    def generate_summary_report(
        self,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> dict[str, Any]:
        """Generate a structured summary suitable for rendering."""
        summary = self.store.get_summary(from_date=from_date, to_date=to_date)
        changes = self.store.query_changes(from_date=from_date, to_date=to_date)

        # Get per-metric failure counts
        runs = self.store.query_runs(
            status="failed", from_date=from_date, to_date=to_date, limit=100_000
        )
        metric_failures: dict[str, int] = {}
        for run in runs:
            name = run["metric_name"]
            metric_failures[name] = metric_failures.get(name, 0) + 1

        return {
            "period": {
                "from": from_date.isoformat() if from_date else "beginning",
                "to": to_date.isoformat() if to_date else "now",
            },
            "overall": summary,
            "metric_failures": dict(
                sorted(metric_failures.items(), key=lambda x: x[1], reverse=True)
            ),
            "total_definition_changes": len(changes),
        }
