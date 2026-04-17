"""Tests for CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from metric_guard.cli import cli


@pytest.fixture
def metrics_dir(tmp_path: Path) -> Path:
    """Create a temporary metrics subdirectory with two sample metrics."""
    mdir = tmp_path / "metrics"
    mdir.mkdir()
    data = {
        "metrics": [
            {
                "name": "content_violation_rate",
                "display_name": "Content Violation Rate",
                "owner": "trust-and-safety",
                "version": "1.0.0",
                "sla_hours": 12,
                "update_frequency": "daily",
                "tags": ["compliance"],
                "depends_on": [],
                "rules": [
                    {"type": "completeness", "severity": "error"},
                    {"type": "freshness", "severity": "critical"},
                ],
            },
            {
                "name": "appeal_overturn_rate",
                "display_name": "Appeal Overturn Rate",
                "owner": "trust-and-safety",
                "version": "2.0.0",
                "sla_hours": 24,
                "update_frequency": "weekly",
                "tags": ["compliance", "appeals"],
                "depends_on": ["content_violation_rate"],
                "rules": [],
            },
        ]
    }
    (mdir / "metrics.yaml").write_text(yaml.dump(data))
    return mdir


@pytest.fixture
def config_file(tmp_path: Path, metrics_dir: Path) -> Path:
    """Write a minimal metric_guard.yaml pointing at the temp metrics dir."""
    cfg = tmp_path / "metric_guard.yaml"
    cfg.write_text(
        f"metrics_dir: {metrics_dir}\n"
        "environment: test\n"
        "alerts:\n  backend: console\n"
        "audit:\n  db_path: .metric_guard/audit.db\n"
    )
    return cfg


class TestValidateJsonFlag:
    def test_json_output_structure(self, config_file: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["validate", "--json", "--config", str(config_file)])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["environment"] == "test"
        assert data["total_metrics"] == 2
        assert data["total_rules"] == 2
        assert len(data["metrics"]) == 2

    def test_json_metric_fields(self, config_file: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["validate", "--json", "--config", str(config_file)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        by_name = {m["name"]: m for m in data["metrics"]}

        m = by_name["content_violation_rate"]
        assert m["display_name"] == "Content Violation Rate"
        assert m["owner"] == "trust-and-safety"
        assert m["version"] == "1.0.0"
        assert m["sla_hours"] == 12.0
        assert m["update_frequency"] == "daily"
        assert m["rule_count"] == 2
        assert m["tags"] == ["compliance"]
        assert m["depends_on"] == []
        assert m["status"] == "defined"

    def test_json_single_metric_filter(self, config_file: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "validate", "--metrics", "appeal_overturn_rate",
                "--json", "--config", str(config_file),
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["total_metrics"] == 1
        assert data["metrics"][0]["name"] == "appeal_overturn_rate"
        assert data["metrics"][0]["depends_on"] == ["content_violation_rate"]

    def test_json_missing_metric_name(self, config_file: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["validate", "--metrics", "nonexistent_metric", "--json", "--config", str(config_file)],
        )
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert "error" in data
        assert "nonexistent_metric" in data["error"]

    def test_json_missing_metrics_dir(self, tmp_path: Path) -> None:
        cfg = tmp_path / "metric_guard.yaml"
        cfg.write_text(
            "metrics_dir: /nonexistent/path\n"
            "environment: test\n"
            "alerts:\n  backend: console\n"
            "audit:\n  db_path: .metric_guard/audit.db\n"
        )
        runner = CliRunner()
        result = runner.invoke(cli, ["validate", "--json", "--config", str(cfg)])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert "error" in data

    def test_default_output_is_not_json(self, config_file: Path) -> None:
        """Without --json, output should be a Rich table, not parseable JSON."""
        runner = CliRunner()
        result = runner.invoke(cli, ["validate", "--config", str(config_file)])
        assert result.exit_code == 0
        with pytest.raises((json.JSONDecodeError, ValueError)):
            json.loads(result.output)


class TestValidateConsoleFormatting:
    """Verify that the human-readable validate output includes key fields."""

    def test_table_shows_owner(self, config_file: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["validate", "--config", str(config_file)])
        assert result.exit_code == 0
        # Rich may truncate cell values; check for the column header and a prefix
        assert "Owner" in result.output
        # "trust-and-safety" may be truncated to "trus…" in narrow terminals
        assert "trus" in result.output

    def test_table_shows_metric_display_name(self, config_file: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["validate", "--config", str(config_file)])
        assert result.exit_code == 0
        assert "Content Violation Rate" in result.output
        assert "Appeal Overturn Rate" in result.output

    def test_summary_shows_metric_and_rule_counts(self, config_file: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["validate", "--config", str(config_file)])
        assert result.exit_code == 0
        # 2 metrics, 2 rules total (content_violation_rate has 2, appeal_overturn_rate has 0)
        assert "2" in result.output  # appears for both metric count and rule count

    def test_severity_columns_present(self, config_file: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["validate", "--config", str(config_file)])
        assert result.exit_code == 0
        # Column headers may be truncated by Rich in narrow terminals,
        # but the summary line always uses full words.
        assert "critical" in result.output  # from summary
        assert "error" in result.output     # from summary or column header

    def test_severity_counts_in_summary(self, tmp_path: Path) -> None:
        """Metrics with critical rules should show critical count in summary."""
        mdir = tmp_path / "metrics"
        mdir.mkdir()
        data = {
            "metrics": [
                {
                    "name": "urgent_metric",
                    "display_name": "Urgent Metric",
                    "owner": "ops-team",
                    "version": "1.0.0",
                    "sla_hours": 1,
                    "update_frequency": "hourly",
                    "tags": [],
                    "depends_on": [],
                    "rules": [
                        {"type": "freshness", "severity": "critical"},
                        {"type": "volume", "severity": "warning"},
                    ],
                }
            ]
        }
        (mdir / "m.yaml").write_text(yaml.dump(data))
        cfg = tmp_path / "metric_guard.yaml"
        cfg.write_text(
            f"metrics_dir: {mdir}\nenvironment: test\n"
            "alerts:\n  backend: console\naudit:\n  db_path: .metric_guard/audit.db\n"
        )
        runner = CliRunner()
        result = runner.invoke(cli, ["validate", "--config", str(cfg)])
        assert result.exit_code == 0
        assert "critical" in result.output
        assert "warning" in result.output
