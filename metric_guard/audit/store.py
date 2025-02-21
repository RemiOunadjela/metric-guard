"""SQLite-backed audit storage for validation run history."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from metric_guard.rules.base import ValidationResult


class AuditStore:
    """Immutable audit trail for validation results.

    Every validation run is recorded with full context -- what was checked,
    what passed, what failed, and when. This is what you hand to auditors
    when they ask "how do you know your metrics are reliable?"
    """

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS validation_runs (
        run_id TEXT PRIMARY KEY,
        metric_name TEXT NOT NULL,
        rule_name TEXT NOT NULL,
        status TEXT NOT NULL,
        severity TEXT NOT NULL,
        message TEXT,
        details TEXT,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS metric_changes (
        change_id TEXT PRIMARY KEY,
        metric_name TEXT NOT NULL,
        field_name TEXT NOT NULL,
        old_value TEXT,
        new_value TEXT,
        changed_by TEXT,
        changed_at TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_runs_metric ON validation_runs(metric_name);
    CREATE INDEX IF NOT EXISTS idx_runs_status ON validation_runs(status);
    CREATE INDEX IF NOT EXISTS idx_runs_created ON validation_runs(created_at);
    CREATE INDEX IF NOT EXISTS idx_changes_metric ON metric_changes(metric_name);
    """

    def __init__(self, db_path: str | Path = ".metric_guard/audit.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(self._SCHEMA)
        self._conn.commit()

    def record_result(self, result: ValidationResult) -> str:
        """Store a validation result. Returns the run_id."""
        run_id = str(uuid.uuid4())
        self._conn.execute(
            """INSERT INTO validation_runs
               (run_id, metric_name, rule_name, status, severity, message, details, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id,
                result.metric_name,
                result.rule_name,
                result.status.value,
                result.severity.value,
                result.message,
                json.dumps(result.details),
                result.timestamp.isoformat(),
            ),
        )
        self._conn.commit()
        return run_id

    def record_batch(self, results: list[ValidationResult]) -> list[str]:
        """Store multiple results in a single transaction."""
        run_ids = []
        for result in results:
            run_id = str(uuid.uuid4())
            run_ids.append(run_id)
            self._conn.execute(
                """INSERT INTO validation_runs
                   (run_id, metric_name, rule_name, status, severity, message, details, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_id,
                    result.metric_name,
                    result.rule_name,
                    result.status.value,
                    result.severity.value,
                    result.message,
                    json.dumps(result.details),
                    result.timestamp.isoformat(),
                ),
            )
        self._conn.commit()
        return run_ids

    def record_change(
        self,
        metric_name: str,
        field_name: str,
        old_value: Any,
        new_value: Any,
        changed_by: str = "",
    ) -> str:
        """Record a metric definition change."""
        change_id = str(uuid.uuid4())
        self._conn.execute(
            """INSERT INTO metric_changes
               (change_id, metric_name, field_name, old_value, new_value, changed_by, changed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                change_id,
                metric_name,
                field_name,
                json.dumps(old_value),
                json.dumps(new_value),
                changed_by,
                datetime.utcnow().isoformat(),
            ),
        )
        self._conn.commit()
        return change_id

    def query_runs(
        self,
        metric_name: str | None = None,
        status: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Query validation run history."""
        conditions: list[str] = []
        params: list[Any] = []

        if metric_name:
            conditions.append("metric_name = ?")
            params.append(metric_name)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if from_date:
            conditions.append("created_at >= ?")
            params.append(from_date.isoformat())
        if to_date:
            conditions.append("created_at <= ?")
            params.append(to_date.isoformat())

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"SELECT * FROM validation_runs {where} ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def query_changes(
        self,
        metric_name: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Query metric change history."""
        conditions: list[str] = []
        params: list[Any] = []

        if metric_name:
            conditions.append("metric_name = ?")
            params.append(metric_name)
        if from_date:
            conditions.append("changed_at >= ?")
            params.append(from_date.isoformat())
        if to_date:
            conditions.append("changed_at <= ?")
            params.append(to_date.isoformat())

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"SELECT * FROM metric_changes {where} ORDER BY changed_at DESC"

        rows = self._conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def get_summary(
        self,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> dict[str, Any]:
        """Get aggregate summary of validation runs."""
        conditions: list[str] = []
        params: list[Any] = []
        if from_date:
            conditions.append("created_at >= ?")
            params.append(from_date.isoformat())
        if to_date:
            conditions.append("created_at <= ?")
            params.append(to_date.isoformat())

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        total = self._conn.execute(
            f"SELECT COUNT(*) FROM validation_runs {where}", params
        ).fetchone()[0]

        status_counts = {}
        for row in self._conn.execute(
            f"SELECT status, COUNT(*) as cnt FROM validation_runs {where} GROUP BY status",
            params,
        ).fetchall():
            status_counts[row["status"]] = row["cnt"]

        severity_counts = {}
        fail_where = f"{where} AND status = 'failed'" if where else "WHERE status = 'failed'"
        for row in self._conn.execute(
            f"SELECT severity, COUNT(*) as cnt FROM validation_runs {fail_where} GROUP BY severity",
            params,
        ).fetchall():
            severity_counts[row["severity"]] = row["cnt"]

        return {
            "total_runs": total,
            "by_status": status_counts,
            "failures_by_severity": severity_counts,
        }

    def close(self) -> None:
        self._conn.close()
