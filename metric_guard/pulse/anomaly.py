"""Anomaly detection using statistical methods."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from metric_guard.pulse.baseline import Baseline, BaselineComputer


class AnomalyMethod(str, Enum):
    Z_SCORE = "z_score"
    IQR = "iqr"
    MODIFIED_Z = "modified_z"


@dataclass(frozen=True)
class AnomalyResult:
    """Result of a single anomaly check."""

    is_anomaly: bool
    value: float
    method: AnomalyMethod
    score: float
    threshold: float
    direction: str  # "high", "low", or "none"


class AnomalyDetector:
    """Detect anomalies in metric time series.

    Supports multiple detection methods. In practice, Z-score works well
    for normally distributed metrics, IQR is more robust to outliers,
    and modified Z-score (using MAD) handles skewed distributions.
    """

    def __init__(
        self,
        method: AnomalyMethod | str = AnomalyMethod.Z_SCORE,
        z_threshold: float = 3.0,
        iqr_multiplier: float = 1.5,
    ) -> None:
        if isinstance(method, str):
            method = AnomalyMethod(method)
        self.method = method
        self.z_threshold = z_threshold
        self.iqr_multiplier = iqr_multiplier
        self._baseline_computer = BaselineComputer()

    def check(self, value: float, baseline: Baseline) -> AnomalyResult:
        """Check a single value against a baseline."""
        if self.method == AnomalyMethod.Z_SCORE:
            return self._check_zscore(value, baseline)
        elif self.method == AnomalyMethod.IQR:
            return self._check_iqr(value, baseline)
        else:
            return self._check_modified_z(value, baseline)

    def detect_all(
        self,
        values: Sequence[float],
        window: int = 30,
    ) -> list[AnomalyResult | None]:
        """Run anomaly detection over an entire series using rolling baselines.

        Returns None for positions where no baseline is available.
        """
        baselines = self._baseline_computer.compute_rolling(values, window=window)
        results: list[AnomalyResult | None] = []
        for i, (val, bl) in enumerate(zip(values, baselines)):
            if bl is None:
                results.append(None)
            else:
                results.append(self.check(val, bl))
        return results

    def _check_zscore(self, value: float, baseline: Baseline) -> AnomalyResult:
        if baseline.std == 0:
            score = 0.0 if value == baseline.mean else float("inf")
        else:
            score = abs(value - baseline.mean) / baseline.std

        direction = "none"
        if score > self.z_threshold:
            direction = "high" if value > baseline.mean else "low"

        return AnomalyResult(
            is_anomaly=score > self.z_threshold,
            value=value,
            method=AnomalyMethod.Z_SCORE,
            score=round(score, 4),
            threshold=self.z_threshold,
            direction=direction,
        )

    def _check_iqr(self, value: float, baseline: Baseline) -> AnomalyResult:
        lower = baseline.q1 - self.iqr_multiplier * baseline.iqr
        upper = baseline.q3 + self.iqr_multiplier * baseline.iqr

        is_anomaly = value < lower or value > upper
        # Use distance from nearest bound as score
        if value < lower:
            score = (lower - value) / baseline.iqr if baseline.iqr > 0 else float("inf")
            direction = "low"
        elif value > upper:
            score = (value - upper) / baseline.iqr if baseline.iqr > 0 else float("inf")
            direction = "high"
        else:
            score = 0.0
            direction = "none"

        return AnomalyResult(
            is_anomaly=is_anomaly,
            value=value,
            method=AnomalyMethod.IQR,
            score=round(score, 4),
            threshold=self.iqr_multiplier,
            direction=direction,
        )

    def _check_modified_z(self, value: float, baseline: Baseline) -> AnomalyResult:
        # Modified Z-score uses median absolute deviation (MAD)
        # We approximate MAD from the baseline's IQR: MAD ~ IQR / 1.3489
        mad = baseline.iqr / 1.3489 if baseline.iqr > 0 else 0.0
        if mad == 0:
            score = 0.0 if value == baseline.median else float("inf")
        else:
            score = 0.6745 * abs(value - baseline.median) / mad

        direction = "none"
        if score > self.z_threshold:
            direction = "high" if value > baseline.median else "low"

        return AnomalyResult(
            is_anomaly=score > self.z_threshold,
            value=value,
            method=AnomalyMethod.MODIFIED_Z,
            score=round(score, 4),
            threshold=self.z_threshold,
            direction=direction,
        )
