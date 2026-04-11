# metric-guard

[![CI](https://github.com/RemiOunadjela/metric-guard/actions/workflows/ci.yml/badge.svg)](https://github.com/RemiOunadjela/metric-guard/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**Automated data quality for compliance metrics.**

A lightweight Python framework for monitoring, validating, and alerting on data quality issues in compliance and regulatory metrics pipelines. Think "Great Expectations meets regulatory reporting" -- purpose-built for teams that file transparency reports, DSA disclosures, or any recurring regulatory submission where bad data means bad outcomes.

---

## Why metric-guard?

I built this after spending too many quarters discovering data quality issues during the final review of regulatory filings. The pattern was always the same: a silent pipeline failure three weeks ago, a metric that looked plausible but was stale, a denominator that quietly changed definition. By the time we caught it, the filing deadline was 48 hours away and we were scrambling.

The existing tools (Great Expectations, dbt tests, Monte Carlo) are excellent for general data quality. But compliance metrics have specific needs:

- **Audit trails are mandatory**, not nice-to-have. Regulators want to see when definitions changed and what you validated.
- **Freshness SLAs are non-negotiable.** A metric that is 36 hours old is worse than a metric that is missing -- it looks right but isn't.
- **Metric interdependencies matter.** If your proactive detection rate depends on total enforcement actions, and enforcement actions are stale, both metrics are compromised.
- **You need to catch drift, not just nulls.** A gradual 15% shift in violation rate distribution over 6 weeks might be real -- or it might be a labeling pipeline bug.

metric-guard is designed for teams that went from quarterly to weekly data quality cycles and need tooling that understands the compliance context.

## Quick Start

### Install

```bash
pip install metric-guard
```

### Define your metrics

Create a YAML file with your metric definitions:

```yaml
# metrics/transparency.yaml
metrics:
  - name: content_violation_rate
    display_name: "Content Violation Rate"
    owner: trust-and-safety
    business_definition: >
      Fraction of reviewed content flagged as policy violations.
      Reported quarterly in transparency disclosures.
    sql_reference: >
      SELECT COUNT(CASE WHEN decision = 'violation' THEN 1 END)::float
      / NULLIF(COUNT(*), 0) FROM content_review_decisions
      WHERE review_date BETWEEN :start AND :end
    update_frequency: daily
    sla_hours: 12
    tags: [compliance, transparency, tier-1]
    version: "2.1.0"
    rules:
      - type: completeness
        params:
          required_columns: [review_id, decision, review_date]
        severity: critical
      - type: freshness
        severity: critical
      - type: volume
        params: { min_count: 1000 }
        severity: error
      - type: range
        params: { min_value: 0.0, max_value: 1.0 }
        severity: critical

  - name: proactive_detection_rate
    display_name: "Proactive Detection Rate"
    owner: trust-and-safety
    business_definition: >
      Share of violations detected by automated systems before user reports.
    update_frequency: daily
    sla_hours: 12
    depends_on: [content_violation_rate]
    version: "1.3.0"
    rules:
      - type: freshness
        severity: error
      - type: distribution
        params: { method: ks, p_value_threshold: 0.01 }
        severity: warning
```

### Run validations

```python
from metric_guard.registry.loader import load_metrics
from metric_guard.registry.graph import DependencyGraph
from metric_guard.rules.completeness import CompletenessRule
from metric_guard.rules.freshness import FreshnessRule
from metric_guard.audit.store import AuditStore

# Load and resolve dependencies
metrics = load_metrics("metrics/transparency.yaml")
graph = DependencyGraph(metrics)
order = graph.topological_order()

# Validate
store = AuditStore()
metric = graph.get_metric("content_violation_rate")

completeness = CompletenessRule(required_columns=["review_id", "decision"])
result = completeness.validate(metric, your_data)
store.record_result(result)

freshness = FreshnessRule()
result = freshness.validate(metric, latest_timestamp)
store.record_result(result)
```

### CLI

```bash
# Scaffold a new project
metric-guard init

# Validate all metrics
metric-guard validate --metrics all --env production

# Start pulse monitoring
metric-guard pulse --schedule "0 */6 * * *"

# Export audit trail
metric-guard audit --from 2024-01-01 --to 2024-06-30 --format json -o report.json

# View metric health dashboard
metric-guard status
```

### Example validation output

```
                   Validation Results (production)
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━━┳━━━━━━┳━━━━━━━━━┓
┃ Metric                    ┃ Rules ┃ Version ┃  SLA ┃ Status  ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━━╇━━━━━━╇━━━━━━━━━┩
│ Content Violation Rate    │     4 │ 2.1.0   │ 12h  │ defined │
│ Proactive Detection Rate  │     2 │ 1.3.0   │ 12h  │ defined │
│ Appeal Overturn Rate      │     4 │ 1.0.2   │ 24h  │ defined │
│ Median Response Time      │     3 │ 1.1.0   │  6h  │ defined │
│ Total Enforcement Actions │     3 │ 1.0.0   │ 12h  │ defined │
└───────────────────────────┴───────┴─────────┴──────┴─────────┘

5 metric(s) loaded with 16 validation rule(s).
```

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                     CLI / API                        │
├──────────────────────────────────────────────────────┤
│  Metric Registry     │  Pulse Monitor                │
│  ├─ YAML Loader      │  ├─ Cron Scheduler            │
│  ├─ Dependency Graph  │  ├─ Baseline Computer         │
│  └─ Version Tracking  │  └─ Anomaly Detector          │
├──────────────────────┼───────────────────────────────┤
│  Validation Rules    │  Alerting                     │
│  ├─ Completeness     │  ├─ Console                   │
│  ├─ Freshness        │  ├─ Slack                     │
│  ├─ Volume           │  ├─ PagerDuty                 │
│  ├─ Distribution     │  ├─ Deduplication             │
│  ├─ Consistency      │  └─ Escalation                │
│  ├─ Monotonicity     ├───────────────────────────────┤
│  ├─ Range            │  Audit Trail                  │
│  └─ Custom (@rule)   │  ├─ SQLite Store              │
│                      │  └─ CSV/JSON Export            │
└──────────────────────┴───────────────────────────────┘
```

## Custom Rules

Define one-off business rules with the `@rule` decorator:

```python
from metric_guard.rules.custom import rule
from metric_guard.registry.metric import Severity

@rule(name="week_over_week_stability", severity=Severity.WARNING)
def check_wow(metric, data):
    current, previous = data["current"], data["previous"]
    change = abs(current - previous) / abs(previous) if previous else 0
    if change > 0.30:
        return False, f"WoW change of {change:.0%} exceeds 30% threshold"
    return True, f"WoW change {change:.0%} within tolerance"
```

## Anomaly Detection

Built-in statistical methods for catching drift before it hits your reports:

```python
from metric_guard.pulse.anomaly import AnomalyDetector
from metric_guard.pulse.baseline import BaselineComputer

computer = BaselineComputer()
baseline = computer.compute(historical_values)

detector = AnomalyDetector(method="z_score", z_threshold=3.0)
result = detector.check(today_value, baseline)
if result.is_anomaly:
    print(f"Anomaly detected: {result.direction} (z={result.score:.2f})")
```

Supported methods: Z-score, IQR, Modified Z-score (MAD-based).

## Comparison with Great Expectations

| | metric-guard | Great Expectations |
|---|---|---|
| **Focus** | Compliance metrics | General data quality |
| **Audit trail** | Built-in, SQLite-backed | Requires Data Docs setup |
| **Metric dependencies** | First-class DAG | Not built-in |
| **Anomaly detection** | Built-in (Z-score, IQR) | Via plugins |
| **Setup overhead** | `pip install` + YAML | Significant config |
| **Distribution checks** | KS test, chi-squared | Expectation-based |
| **Custom rules** | `@rule` decorator | Custom Expectation class |

metric-guard is not a replacement for Great Expectations. If you need schema validation on hundreds of tables, use GX. If you need purpose-built monitoring for the 15 metrics that appear in your regulatory filings, metric-guard gets you there faster.

## Development

```bash
git clone https://github.com/RemiOunadjela/metric-guard.git
cd metric-guard
pip install -e ".[dev]"
pytest
```

## Related Projects

- **[safetybench](https://github.com/RemiOunadjela/safetybench)** -- Benchmarking framework for evaluating content moderation models against T&S-specific metrics.
- **[crisis-lens](https://github.com/RemiOunadjela/crisis-lens)** -- Real-time crisis detection and triage for Trust & Safety text streams.
- **[transparency-engine](https://github.com/RemiOunadjela/transparency-engine)** -- Regulatory-compliant transparency report generation across DSA, OSA, and custom frameworks.

## License

MIT
