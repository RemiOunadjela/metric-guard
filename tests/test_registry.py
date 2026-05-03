"""Tests for metric registry: definitions, loading, and dependency graph."""

from pathlib import Path

import pytest
import yaml

from metric_guard.registry.graph import CyclicDependencyError, DependencyGraph
from metric_guard.registry.loader import load_metrics, load_metrics_from_dir
from metric_guard.registry.metric import MetricDefinition, UpdateFrequency


@pytest.fixture
def sample_metric() -> MetricDefinition:
    return MetricDefinition(
        name="content_violation_rate",
        display_name="Content Violation Rate",
        owner="trust-and-safety",
        business_definition="Fraction of content flagged as violations",
        update_frequency=UpdateFrequency.DAILY,
        sla_hours=12.0,
        version="2.1.0",
        tags=["compliance", "transparency"],
    )


@pytest.fixture
def metrics_yaml(tmp_path: Path) -> Path:
    data = {
        "metrics": [
            {
                "name": "metric_a",
                "display_name": "Metric A",
                "owner": "team-x",
                "version": "1.0.0",
            },
            {
                "name": "metric_b",
                "display_name": "Metric B",
                "owner": "team-y",
                "depends_on": ["metric_a"],
                "version": "1.0.0",
            },
        ]
    }
    yaml_file = tmp_path / "metrics.yaml"
    yaml_file.write_text(yaml.dump(data))
    return yaml_file


class TestMetricDefinition:
    def test_creation(self, sample_metric: MetricDefinition) -> None:
        assert sample_metric.name == "content_violation_rate"
        assert sample_metric.sla_hours == 12.0
        assert sample_metric.update_frequency == UpdateFrequency.DAILY

    def test_qualified_name(self, sample_metric: MetricDefinition) -> None:
        assert sample_metric.qualified_name == "content_violation_rate@2.1.0"

    def test_equality_by_name(self) -> None:
        m1 = MetricDefinition(name="test", version="1.0.0")
        m2 = MetricDefinition(name="test", version="2.0.0")
        assert m1 == m2

    def test_hash_by_name(self) -> None:
        m1 = MetricDefinition(name="test", version="1.0.0")
        m2 = MetricDefinition(name="test", version="2.0.0")
        assert hash(m1) == hash(m2)
        assert len({m1, m2}) == 1

    def test_default_values(self) -> None:
        m = MetricDefinition(name="simple")
        assert m.sla_hours == 24.0
        assert m.update_frequency == UpdateFrequency.DAILY
        assert m.tags == []
        assert m.depends_on == []


class TestLoader:
    def test_load_metrics_from_file(self, metrics_yaml: Path) -> None:
        metrics = load_metrics(metrics_yaml)
        assert len(metrics) == 2
        assert metrics[0].name == "metric_a"
        assert metrics[1].depends_on == ["metric_a"]

    def test_load_single_metric(self, tmp_path: Path) -> None:
        data = {"name": "solo_metric", "owner": "me"}
        yaml_file = tmp_path / "solo.yaml"
        yaml_file.write_text(yaml.dump(data))
        metrics = load_metrics(yaml_file)
        assert len(metrics) == 1
        assert metrics[0].name == "solo_metric"

    def test_load_empty_file(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "empty.yaml"
        yaml_file.write_text("")
        assert load_metrics(yaml_file) == []

    def test_load_from_directory(self, tmp_path: Path) -> None:
        for i in range(3):
            data = {"metrics": [{"name": f"metric_{i}"}]}
            (tmp_path / f"batch_{i}.yaml").write_text(yaml.dump(data))
        metrics = load_metrics_from_dir(tmp_path)
        assert len(metrics) == 3

    def test_dedup_on_directory_load(self, tmp_path: Path) -> None:
        for suffix in ["a", "b"]:
            data = {"metrics": [{"name": "same_metric", "owner": f"team_{suffix}"}]}
            (tmp_path / f"file_{suffix}.yaml").write_text(yaml.dump(data))
        metrics = load_metrics_from_dir(tmp_path)
        assert len(metrics) == 1
        # Last file wins
        assert metrics[0].owner == "team_b"

    def test_missing_directory_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_metrics_from_dir("/nonexistent/path")


class TestSchemaValidation:
    def test_missing_name_raises(self, tmp_path: Path) -> None:
        data = {"metrics": [{"owner": "team-x", "sla_hours": 24}]}
        yaml_file = tmp_path / "bad.yaml"
        yaml_file.write_text(yaml.dump(data))
        with pytest.raises(ValueError, match="'name' is a required property"):
            load_metrics(yaml_file)

    def test_invalid_update_frequency_raises(self, tmp_path: Path) -> None:
        data = {"metrics": [{"name": "m", "update_frequency": "fortnightly"}]}
        yaml_file = tmp_path / "bad.yaml"
        yaml_file.write_text(yaml.dump(data))
        with pytest.raises(ValueError, match="is not one of"):
            load_metrics(yaml_file)

    def test_invalid_rule_type_raises(self, tmp_path: Path) -> None:
        data = {"metrics": [{"name": "m", "rules": [{"type": "unknown_rule"}]}]}
        yaml_file = tmp_path / "bad.yaml"
        yaml_file.write_text(yaml.dump(data))
        with pytest.raises(ValueError, match="is not one of"):
            load_metrics(yaml_file)

    def test_invalid_severity_raises(self, tmp_path: Path) -> None:
        data = {"metrics": [{"name": "m", "rules": [{"type": "freshness", "severity": "blocker"}]}]}
        yaml_file = tmp_path / "bad.yaml"
        yaml_file.write_text(yaml.dump(data))
        with pytest.raises(ValueError, match="is not one of"):
            load_metrics(yaml_file)

    def test_sla_hours_wrong_type_raises(self, tmp_path: Path) -> None:
        data = {"metrics": [{"name": "m", "sla_hours": "not-a-number"}]}
        yaml_file = tmp_path / "bad.yaml"
        yaml_file.write_text(yaml.dump(data))
        with pytest.raises(ValueError, match="is not of type"):
            load_metrics(yaml_file)

    def test_tags_not_list_raises(self, tmp_path: Path) -> None:
        data = {"metrics": [{"name": "m", "tags": "compliance"}]}
        yaml_file = tmp_path / "bad.yaml"
        yaml_file.write_text(yaml.dump(data))
        with pytest.raises(ValueError, match="is not of type"):
            load_metrics(yaml_file)

    def test_metrics_not_list_raises(self, tmp_path: Path) -> None:
        data = {"metrics": "not-a-list"}
        yaml_file = tmp_path / "bad.yaml"
        yaml_file.write_text(yaml.dump(data))
        with pytest.raises(ValueError, match="must contain a list"):
            load_metrics(yaml_file)

    def test_error_message_includes_metric_name(self, tmp_path: Path) -> None:
        data = {"metrics": [{"name": "bad_metric", "update_frequency": "fortnightly"}]}
        yaml_file = tmp_path / "bad.yaml"
        yaml_file.write_text(yaml.dump(data))
        with pytest.raises(ValueError, match="bad_metric"):
            load_metrics(yaml_file)

    def test_valid_metric_passes_schema(self, tmp_path: Path) -> None:
        data = {
            "metrics": [
                {
                    "name": "my_metric",
                    "owner": "team-a",
                    "update_frequency": "daily",
                    "sla_hours": 12.0,
                    "tags": ["compliance"],
                    "rules": [{"type": "freshness", "severity": "error"}],
                }
            ]
        }
        yaml_file = tmp_path / "valid.yaml"
        yaml_file.write_text(yaml.dump(data))
        metrics = load_metrics(yaml_file)
        assert len(metrics) == 1
        assert metrics[0].name == "my_metric"

    def test_all_update_frequencies_valid(self, tmp_path: Path) -> None:
        for freq in ["hourly", "daily", "weekly", "monthly", "quarterly"]:
            data = {"metrics": [{"name": "m", "update_frequency": freq}]}
            yaml_file = tmp_path / f"{freq}.yaml"
            yaml_file.write_text(yaml.dump(data))
            assert load_metrics(yaml_file)[0].name == "m"

    def test_all_rule_types_valid(self, tmp_path: Path) -> None:
        rule_types = ["completeness", "freshness", "volume", "range", "distribution",
                      "consistency", "monotonicity", "custom"]
        data = {"metrics": [{"name": "m", "rules": [{"type": t} for t in rule_types]}]}
        yaml_file = tmp_path / "all_rules.yaml"
        yaml_file.write_text(yaml.dump(data))
        metrics = load_metrics(yaml_file)
        assert len(metrics[0].rules) == len(rule_types)


class TestDependencyGraph:
    def test_topological_order(self) -> None:
        metrics = [
            MetricDefinition(name="upstream"),
            MetricDefinition(name="mid", depends_on=["upstream"]),
            MetricDefinition(name="downstream", depends_on=["mid"]),
        ]
        graph = DependencyGraph(metrics)
        order = graph.topological_order()
        assert order.index("upstream") < order.index("mid")
        assert order.index("mid") < order.index("downstream")

    def test_upstream_traversal(self) -> None:
        metrics = [
            MetricDefinition(name="a"),
            MetricDefinition(name="b", depends_on=["a"]),
            MetricDefinition(name="c", depends_on=["b"]),
        ]
        graph = DependencyGraph(metrics)
        assert graph.upstream("c") == {"a", "b"}
        assert graph.upstream("a") == set()

    def test_downstream_traversal(self) -> None:
        metrics = [
            MetricDefinition(name="a"),
            MetricDefinition(name="b", depends_on=["a"]),
            MetricDefinition(name="c", depends_on=["a"]),
        ]
        graph = DependencyGraph(metrics)
        assert graph.downstream("a") == {"b", "c"}

    def test_cycle_detection(self) -> None:
        metrics = [
            MetricDefinition(name="x", depends_on=["z"]),
            MetricDefinition(name="y", depends_on=["x"]),
            MetricDefinition(name="z", depends_on=["y"]),
        ]
        graph = DependencyGraph(metrics)
        with pytest.raises(CyclicDependencyError):
            graph.topological_order()

    def test_independent_metrics(self) -> None:
        metrics = [
            MetricDefinition(name="a"),
            MetricDefinition(name="b"),
            MetricDefinition(name="c"),
        ]
        graph = DependencyGraph(metrics)
        order = graph.topological_order()
        assert set(order) == {"a", "b", "c"}
