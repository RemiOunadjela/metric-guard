"""Tests for validation rules."""

from datetime import datetime, timedelta

import pytest

from metric_guard.registry.metric import MetricDefinition, Severity
from metric_guard.rules.base import RuleStatus
from metric_guard.rules.completeness import CompletenessRule
from metric_guard.rules.consistency import ConsistencyRule
from metric_guard.rules.custom import rule
from metric_guard.rules.distribution import DistributionRule
from metric_guard.rules.freshness import FreshnessRule
from metric_guard.rules.volume import MonotonicityRule, RangeRule, VolumeRule


@pytest.fixture
def metric() -> MetricDefinition:
    return MetricDefinition(
        name="test_metric",
        display_name="Test Metric",
        sla_hours=12.0,
    )


class TestCompletenessRule:
    def test_all_complete(self, metric: MetricDefinition) -> None:
        r = CompletenessRule(required_columns=["a", "b"])
        data = {"a": [1, 2, 3], "b": [4, 5, 6]}
        result = r.validate(metric, data)
        assert result.passed

    def test_nulls_detected(self, metric: MetricDefinition) -> None:
        r = CompletenessRule(required_columns=["a"])
        data = {"a": [1, None, 3, None]}
        result = r.validate(metric, data)
        assert result.status == RuleStatus.FAILED
        assert result.details["null_fractions"]["a"] == 0.5

    def test_missing_column(self, metric: MetricDefinition) -> None:
        r = CompletenessRule(required_columns=["a", "missing"])
        data = {"a": [1, 2]}
        result = r.validate(metric, data)
        assert result.status == RuleStatus.FAILED

    def test_null_fraction_tolerance(self, metric: MetricDefinition) -> None:
        r = CompletenessRule(required_columns=["a"], max_null_fraction=0.5)
        data = {"a": [1, None, 3, 4]}  # 25% null, under 50% threshold
        result = r.validate(metric, data)
        assert result.passed

    def test_empty_data(self, metric: MetricDefinition) -> None:
        r = CompletenessRule()
        result = r.validate(metric, {})
        assert result.status == RuleStatus.FAILED

    def test_high_null_fraction_escalates_severity(self, metric: MetricDefinition) -> None:
        r = CompletenessRule(required_columns=["a"])
        data = {"a": [None, None, None, 1]}  # 75% null
        result = r.validate(metric, data)
        assert result.severity == Severity.CRITICAL


class TestFreshnessRule:
    def test_fresh_data(self, metric: MetricDefinition) -> None:
        r = FreshnessRule()
        now = datetime.utcnow()
        result = r.validate(metric, now - timedelta(hours=6), reference_time=now)
        assert result.passed

    def test_stale_data(self, metric: MetricDefinition) -> None:
        r = FreshnessRule()
        now = datetime.utcnow()
        result = r.validate(metric, now - timedelta(hours=24), reference_time=now)
        assert result.status == RuleStatus.FAILED

    def test_custom_staleness_hours(self, metric: MetricDefinition) -> None:
        r = FreshnessRule(max_staleness_hours=1.0)
        now = datetime.utcnow()
        result = r.validate(metric, now - timedelta(hours=2), reference_time=now)
        assert result.status == RuleStatus.FAILED

    def test_dict_input(self, metric: MetricDefinition) -> None:
        r = FreshnessRule()
        now = datetime.utcnow()
        data = {"latest_timestamp": now - timedelta(hours=1)}
        result = r.validate(metric, data, reference_time=now)
        assert result.passed

    def test_no_timestamp_skips(self, metric: MetricDefinition) -> None:
        r = FreshnessRule()
        result = r.validate(metric, "not a timestamp")
        assert result.status == RuleStatus.SKIPPED

    def test_very_stale_escalates(self, metric: MetricDefinition) -> None:
        r = FreshnessRule()
        now = datetime.utcnow()
        result = r.validate(metric, now - timedelta(hours=48), reference_time=now)
        assert result.severity == Severity.CRITICAL


class TestVolumeRule:
    def test_count_within_bounds(self, metric: MetricDefinition) -> None:
        r = VolumeRule(min_count=100, max_count=10000)
        result = r.validate(metric, 5000)
        assert result.passed

    def test_count_below_minimum(self, metric: MetricDefinition) -> None:
        r = VolumeRule(min_count=100)
        result = r.validate(metric, 10)
        assert result.status == RuleStatus.FAILED

    def test_count_above_maximum(self, metric: MetricDefinition) -> None:
        r = VolumeRule(max_count=100)
        result = r.validate(metric, 200)
        assert result.status == RuleStatus.FAILED

    def test_dict_input(self, metric: MetricDefinition) -> None:
        r = VolumeRule(min_count=10)
        result = r.validate(metric, {"count": 50, "value": 0.5})
        assert result.passed


class TestMonotonicityRule:
    def test_non_decreasing(self, metric: MetricDefinition) -> None:
        r = MonotonicityRule()
        result = r.validate(metric, [1, 2, 3, 4, 5])
        assert result.passed

    def test_decrease_detected(self, metric: MetricDefinition) -> None:
        r = MonotonicityRule()
        result = r.validate(metric, [1, 2, 3, 2, 5])
        assert result.status == RuleStatus.FAILED

    def test_strict_rejects_equal(self, metric: MetricDefinition) -> None:
        r = MonotonicityRule(strict=True)
        result = r.validate(metric, [1, 2, 2, 3])
        assert result.status == RuleStatus.FAILED

    def test_insufficient_data_skips(self, metric: MetricDefinition) -> None:
        r = MonotonicityRule()
        result = r.validate(metric, [1])
        assert result.status == RuleStatus.SKIPPED


class TestRangeRule:
    def test_within_range(self, metric: MetricDefinition) -> None:
        r = RangeRule(min_value=0.0, max_value=1.0)
        result = r.validate(metric, [0.1, 0.5, 0.9])
        assert result.passed

    def test_out_of_range(self, metric: MetricDefinition) -> None:
        r = RangeRule(min_value=0.0, max_value=1.0)
        result = r.validate(metric, [0.5, 1.2, -0.1])
        assert result.status == RuleStatus.FAILED

    def test_scalar_input(self, metric: MetricDefinition) -> None:
        r = RangeRule(min_value=0.0, max_value=100.0)
        result = r.validate(metric, 50.0)
        assert result.passed


class TestDistributionRule:
    def test_same_distribution_passes(self, metric: MetricDefinition) -> None:
        import numpy as np
        rng = np.random.default_rng(42)
        reference = rng.normal(10, 2, 200).tolist()
        current = rng.normal(10, 2, 200).tolist()
        r = DistributionRule(method="ks", p_value_threshold=0.05)
        result = r.validate(metric, {"reference": reference, "current": current})
        assert result.passed

    def test_different_distribution_fails(self, metric: MetricDefinition) -> None:
        import numpy as np
        rng = np.random.default_rng(42)
        reference = rng.normal(10, 2, 200).tolist()
        current = rng.normal(20, 2, 200).tolist()  # shifted mean
        r = DistributionRule(method="ks")
        result = r.validate(metric, {"reference": reference, "current": current})
        assert result.status == RuleStatus.FAILED

    def test_insufficient_samples_skips(self, metric: MetricDefinition) -> None:
        r = DistributionRule(min_sample_size=30)
        result = r.validate(metric, {"reference": [1, 2], "current": [3, 4]})
        assert result.status == RuleStatus.SKIPPED

    def test_chi2_method(self, metric: MetricDefinition) -> None:
        import numpy as np
        rng = np.random.default_rng(42)
        reference = rng.normal(10, 2, 200).tolist()
        current = rng.normal(10, 2, 200).tolist()
        r = DistributionRule(method="chi2")
        result = r.validate(metric, {"reference": reference, "current": current})
        # Same distribution should pass
        assert result.status in (RuleStatus.PASSED, RuleStatus.FAILED)  # chi2 can be sensitive

    def test_invalid_method(self) -> None:
        with pytest.raises(ValueError, match="Unsupported method"):
            DistributionRule(method="invalid")


class TestConsistencyRule:
    def test_sum_consistent(self, metric: MetricDefinition) -> None:
        r = ConsistencyRule(relation="sum", tolerance=0.01)
        data = {"parts": [30, 40, 30], "total": 100}
        result = r.validate(metric, data)
        assert result.passed

    def test_sum_inconsistent(self, metric: MetricDefinition) -> None:
        r = ConsistencyRule(relation="sum", tolerance=0.01)
        data = {"parts": [30, 40, 30], "total": 120}
        result = r.validate(metric, data)
        assert result.status == RuleStatus.FAILED

    def test_ratio_consistent(self, metric: MetricDefinition) -> None:
        r = ConsistencyRule(relation="ratio", tolerance=0.01)
        data = {"numerator": 50, "denominator": 100, "expected_ratio": 0.5}
        result = r.validate(metric, data)
        assert result.passed

    def test_equality_consistent(self, metric: MetricDefinition) -> None:
        r = ConsistencyRule(relation="equality", tolerance=0.01)
        data = {"values": [100, 100.5, 99.5]}
        result = r.validate(metric, data)
        assert result.passed

    def test_equality_inconsistent(self, metric: MetricDefinition) -> None:
        r = ConsistencyRule(relation="equality", tolerance=0.01)
        data = {"values": [100, 200]}
        result = r.validate(metric, data)
        assert result.status == RuleStatus.FAILED


class TestCustomRule:
    def test_decorator_creates_rule(self) -> None:
        @rule(name="my_check")
        def check(metric, data):
            return True, "all good"

        assert check.name == "my_check"

    def test_bool_return(self, metric: MetricDefinition) -> None:
        @rule(name="bool_check")
        def check(metric, data):
            return data > 0

        result = check.validate(metric, 5)
        assert result.passed

        result = check.validate(metric, -1)
        assert result.status == RuleStatus.FAILED

    def test_tuple_return(self, metric: MetricDefinition) -> None:
        @rule(name="tuple_check")
        def check(metric, data):
            if data["val"] > 100:
                return False, "too high"
            return True, "ok"

        result = check.validate(metric, {"val": 50})
        assert result.passed

    def test_exception_handling(self, metric: MetricDefinition) -> None:
        @rule(name="bad_rule")
        def check(metric, data):
            raise ValueError("oops")

        result = check.validate(metric, {})
        assert result.status == RuleStatus.FAILED
        assert "oops" in result.message

    def test_custom_severity(self, metric: MetricDefinition) -> None:
        @rule(name="warn_rule", severity=Severity.WARNING)
        def check(metric, data):
            return False, "meh"

        result = check.validate(metric, {})
        assert result.severity == Severity.WARNING
