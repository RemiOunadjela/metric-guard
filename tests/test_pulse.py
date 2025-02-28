"""Tests for pulse monitoring: baselines, anomaly detection, scheduler."""

import numpy as np
import pytest

from metric_guard.pulse.anomaly import AnomalyDetector, AnomalyMethod
from metric_guard.pulse.baseline import Baseline, BaselineComputer
from metric_guard.pulse.scheduler import PulseScheduler


class TestBaselineComputer:
    def test_compute_basic(self) -> None:
        bc = BaselineComputer(min_observations=5)
        values = [10.0, 12.0, 11.0, 13.0, 9.0, 10.5, 11.5]
        baseline = bc.compute(values)
        assert baseline is not None
        assert baseline.n_observations == 7
        assert 10.0 < baseline.mean < 12.0

    def test_insufficient_observations(self) -> None:
        bc = BaselineComputer(min_observations=10)
        assert bc.compute([1.0, 2.0, 3.0]) is None

    def test_iqr_bounds(self) -> None:
        bc = BaselineComputer(min_observations=5)
        values = list(range(20))
        baseline = bc.compute([float(v) for v in values])
        assert baseline is not None
        assert baseline.iqr_lower < baseline.q1
        assert baseline.iqr_upper > baseline.q3

    def test_rolling_baseline(self) -> None:
        bc = BaselineComputer(min_observations=3)
        values = [float(i) for i in range(20)]
        rolling = bc.compute_rolling(values, window=5)
        assert len(rolling) == 20
        # First few should be None (not enough history)
        assert rolling[0] is None
        assert rolling[1] is None
        assert rolling[2] is None
        # Later ones should have baselines
        assert rolling[10] is not None


class TestAnomalyDetector:
    @pytest.fixture
    def stable_baseline(self) -> Baseline:
        return Baseline(
            mean=100.0,
            std=5.0,
            median=100.0,
            q1=97.0,
            q3=103.0,
            iqr=6.0,
            min_val=85.0,
            max_val=115.0,
            n_observations=30,
        )

    def test_zscore_normal_value(self, stable_baseline: Baseline) -> None:
        detector = AnomalyDetector(method=AnomalyMethod.Z_SCORE, z_threshold=3.0)
        result = detector.check(102.0, stable_baseline)
        assert not result.is_anomaly
        assert result.direction == "none"

    def test_zscore_anomaly_high(self, stable_baseline: Baseline) -> None:
        detector = AnomalyDetector(method=AnomalyMethod.Z_SCORE, z_threshold=3.0)
        result = detector.check(120.0, stable_baseline)
        assert result.is_anomaly
        assert result.direction == "high"

    def test_zscore_anomaly_low(self, stable_baseline: Baseline) -> None:
        detector = AnomalyDetector(method=AnomalyMethod.Z_SCORE, z_threshold=3.0)
        result = detector.check(80.0, stable_baseline)
        assert result.is_anomaly
        assert result.direction == "low"

    def test_iqr_normal_value(self, stable_baseline: Baseline) -> None:
        detector = AnomalyDetector(method=AnomalyMethod.IQR, iqr_multiplier=1.5)
        result = detector.check(100.0, stable_baseline)
        assert not result.is_anomaly

    def test_iqr_anomaly(self, stable_baseline: Baseline) -> None:
        detector = AnomalyDetector(method=AnomalyMethod.IQR, iqr_multiplier=1.5)
        result = detector.check(130.0, stable_baseline)
        assert result.is_anomaly

    def test_modified_z(self, stable_baseline: Baseline) -> None:
        detector = AnomalyDetector(method=AnomalyMethod.MODIFIED_Z, z_threshold=3.0)
        result = detector.check(100.0, stable_baseline)
        assert not result.is_anomaly

    def test_detect_all(self) -> None:
        detector = AnomalyDetector(method=AnomalyMethod.Z_SCORE, z_threshold=2.0)
        rng = np.random.default_rng(42)
        values = rng.normal(100, 5, 50).tolist()
        values[45] = 200.0  # inject anomaly
        results = detector.detect_all(values, window=20)
        assert len(results) == 50
        # The injected anomaly should be flagged
        assert results[45] is not None
        assert results[45].is_anomaly

    def test_string_method_init(self) -> None:
        detector = AnomalyDetector(method="z_score")
        assert detector.method == AnomalyMethod.Z_SCORE


class TestPulseScheduler:
    def test_add_job(self) -> None:
        scheduler = PulseScheduler()
        scheduler.add_job("test", "*/5 * * * *", lambda: None)
        runs = scheduler.get_next_runs()
        assert len(runs) == 1
        assert runs[0]["name"] == "test"

    def test_invalid_cron(self) -> None:
        scheduler = PulseScheduler()
        with pytest.raises(ValueError, match="Invalid cron"):
            scheduler.add_job("bad", "not-a-cron", lambda: None)

    def test_run_with_max_iterations(self) -> None:
        scheduler = PulseScheduler()
        counter = {"n": 0}

        def tick() -> None:
            counter["n"] += 1

        # Every second
        scheduler.add_job("tick", "* * * * *", tick)
        scheduler.run(max_iterations=2)
        # Should complete without hanging

    def test_stop(self) -> None:
        scheduler = PulseScheduler()
        scheduler.add_job("noop", "* * * * *", lambda: None)
        scheduler.stop()
        assert not scheduler._running
