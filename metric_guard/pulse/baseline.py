"""Historical baseline computation for anomaly detection."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Baseline:
    """Statistical summary of a metric's historical behavior."""

    mean: float
    std: float
    median: float
    q1: float
    q3: float
    iqr: float
    min_val: float
    max_val: float
    n_observations: int

    @property
    def iqr_lower(self) -> float:
        return self.q1 - 1.5 * self.iqr

    @property
    def iqr_upper(self) -> float:
        return self.q3 + 1.5 * self.iqr


class BaselineComputer:
    """Compute rolling baselines from historical metric observations.

    Baselines drive anomaly detection -- without a stable baseline,
    you can't distinguish signal from noise.
    """

    def __init__(self, min_observations: int = 7) -> None:
        self.min_observations = min_observations

    def compute(self, values: Sequence[float]) -> Baseline | None:
        """Compute baseline statistics from a series of historical values.

        Returns None if there are too few observations to form a reliable baseline.
        """
        if len(values) < self.min_observations:
            return None

        arr = np.array(values, dtype=float)
        q1 = float(np.percentile(arr, 25))
        q3 = float(np.percentile(arr, 75))

        return Baseline(
            mean=float(np.mean(arr)),
            std=float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0,
            median=float(np.median(arr)),
            q1=q1,
            q3=q3,
            iqr=q3 - q1,
            min_val=float(np.min(arr)),
            max_val=float(np.max(arr)),
            n_observations=len(arr),
        )

    def compute_rolling(
        self,
        values: Sequence[float],
        window: int = 30,
    ) -> list[Baseline | None]:
        """Compute rolling baselines over a sliding window.

        Returns a list the same length as ``values``, where each entry is
        the baseline computed from the preceding ``window`` observations.
        """
        results: list[Baseline | None] = []
        for i in range(len(values)):
            start = max(0, i - window)
            window_values = values[start:i]
            results.append(self.compute(window_values))
        return results
