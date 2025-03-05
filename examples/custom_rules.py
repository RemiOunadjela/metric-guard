"""Custom rule examples using the @rule decorator."""

from metric_guard.registry.metric import MetricDefinition, Severity
from metric_guard.rules.custom import rule


@rule(name="positive_rate_bounds")
def check_rate_is_valid(metric: MetricDefinition, data: dict) -> tuple[bool, str]:
    """Rates should always be between 0 and 1."""
    rate = data.get("rate")
    if rate is None:
        return False, "No 'rate' field in data"
    if not (0.0 <= rate <= 1.0):
        return False, f"Rate {rate:.4f} is outside [0, 1]"
    return True, f"Rate {rate:.4f} is valid"


@rule(name="week_over_week_stability", severity=Severity.WARNING)
def check_wow_stability(metric: MetricDefinition, data: dict) -> tuple[bool, str]:
    """Flag metrics that swing more than 30% week over week."""
    current = data.get("current_value")
    previous = data.get("previous_value")

    if current is None or previous is None:
        return False, "Missing current or previous value"

    if previous == 0:
        return True, "Previous value is zero, skipping WoW check"

    change = abs(current - previous) / abs(previous)
    if change > 0.30:
        direction = "increased" if current > previous else "decreased"
        return False, f"Metric {direction} by {change:.1%} WoW (threshold: 30%)"

    return True, f"WoW change is {change:.1%}, within tolerance"


def main() -> None:
    metric = MetricDefinition(
        name="proactive_detection_rate",
        display_name="Proactive Detection Rate",
        owner="trust-and-safety",
    )

    # Valid rate
    result = check_rate_is_valid.validate(metric, {"rate": 0.73})
    print(f"{result.rule_name}: {result.status.value} - {result.message}")

    # Invalid rate
    result = check_rate_is_valid.validate(metric, {"rate": 1.05})
    print(f"{result.rule_name}: {result.status.value} - {result.message}")

    # Stable WoW
    result = check_wow_stability.validate(
        metric, {"current_value": 0.73, "previous_value": 0.71}
    )
    print(f"{result.rule_name}: {result.status.value} - {result.message}")

    # Unstable WoW
    result = check_wow_stability.validate(
        metric, {"current_value": 0.73, "previous_value": 0.50}
    )
    print(f"{result.rule_name}: {result.status.value} - {result.message}")


if __name__ == "__main__":
    main()
