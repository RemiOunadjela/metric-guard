"""Distribution validation: statistical tests for data drift."""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy import stats

from metric_guard.registry.metric import MetricDefinition, Severity
from metric_guard.rules.base import RuleStatus, ValidationResult, ValidationRule


class DistributionRule(ValidationRule):
    """Detect distributional shifts using KS test or chi-squared test.

    When the distribution of a compliance metric changes significantly,
    it often means either the underlying phenomenon changed (real signal)
    or the data pipeline broke (false signal). Either way, you want to know.
    """

    name = "distribution"
    default_severity = Severity.WARNING

    def __init__(
        self,
        method: str = "ks",
        p_value_threshold: float = 0.05,
        min_sample_size: int = 30,
    ) -> None:
        if method not in ("ks", "chi2"):
            raise ValueError(f"Unsupported method: {method}. Use 'ks' or 'chi2'.")
        self.method = method
        self.p_value_threshold = p_value_threshold
        self.min_sample_size = min_sample_size

    def validate(
        self,
        metric: MetricDefinition,
        data: Any,
        **kwargs: Any,
    ) -> ValidationResult:
        """Compare two distributions for significant differences.

        Args:
            data: A dict with ``reference`` and ``current`` keys, each containing
                  a list of numeric values.
        """
        if not isinstance(data, dict):
            return self._result(
                metric,
                RuleStatus.SKIPPED,
                "Expected dict with 'reference' and 'current' keys",
            )

        reference = data.get("reference", [])
        current = data.get("current", [])

        if len(reference) < self.min_sample_size or len(current) < self.min_sample_size:
            return self._result(
                metric,
                RuleStatus.SKIPPED,
                f"Insufficient samples (need {self.min_sample_size}, "
                f"got ref={len(reference)}, cur={len(current)})",
            )

        ref_arr = np.array(reference, dtype=float)
        cur_arr = np.array(current, dtype=float)

        if self.method == "ks":
            stat, p_value = stats.ks_2samp(ref_arr, cur_arr)
            test_name = "Kolmogorov-Smirnov"
        else:
            # For chi-squared, bin the data
            combined = np.concatenate([ref_arr, cur_arr])
            bins = np.histogram_bin_edges(combined, bins="auto")
            ref_hist, _ = np.histogram(ref_arr, bins=bins)
            cur_hist, _ = np.histogram(cur_arr, bins=bins)
            # Avoid zero bins
            ref_hist = ref_hist + 1
            cur_hist = cur_hist + 1
            stat, p_value = stats.chisquare(cur_hist, f_exp=ref_hist)
            test_name = "Chi-squared"

        details = {
            "test": test_name,
            "statistic": round(float(stat), 6),
            "p_value": round(float(p_value), 6),
            "threshold": self.p_value_threshold,
            "reference_size": len(reference),
            "current_size": len(current),
        }

        if p_value < self.p_value_threshold:
            return self._result(
                metric,
                RuleStatus.FAILED,
                f"{test_name} test: significant distribution shift "
                f"(p={p_value:.4f} < {self.p_value_threshold})",
                details=details,
            )

        return self._result(
            metric,
            RuleStatus.PASSED,
            f"{test_name} test: no significant shift (p={p_value:.4f})",
            details=details,
        )
