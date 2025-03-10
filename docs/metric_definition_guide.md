# Metric Definition Guide

This guide explains how to define compliance metrics in metric-guard using YAML.

## Anatomy of a Metric Definition

```yaml
metrics:
  - name: content_violation_rate          # unique identifier (snake_case)
    display_name: "Content Violation Rate" # human-readable label
    owner: trust-and-safety               # team or individual responsible
    business_definition: >                # what it measures, in plain language
      Fraction of reviewed content items flagged as violations...
    sql_reference: >                      # reference query (documentation, not executed)
      SELECT COUNT(CASE WHEN decision = 'violation' THEN 1 END)::float / ...
    update_frequency: daily               # hourly | daily | weekly | monthly | quarterly
    sla_hours: 12                         # max acceptable data staleness
    tags:                                 # free-form tags for filtering
      - transparency
      - compliance
    depends_on:                           # upstream metric dependencies
      - total_content_reviewed
    version: "2.1.0"                      # semver for change tracking
    rules:                                # validation rules to apply
      - type: completeness
        params:
          required_columns: ["review_id", "decision"]
        severity: critical
      - type: freshness
        severity: error
```

## Fields Reference

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `name` | Yes | - | Unique snake_case identifier |
| `display_name` | No | same as name | Human-readable label |
| `owner` | No | "" | Responsible team or person |
| `business_definition` | No | "" | What the metric measures |
| `sql_reference` | No | "" | Reference SQL (not executed) |
| `update_frequency` | No | daily | Expected refresh cadence |
| `sla_hours` | No | 24 | Max acceptable staleness in hours |
| `tags` | No | [] | Free-form labels |
| `depends_on` | No | [] | Names of upstream metrics |
| `version` | No | "1.0.0" | Semantic version |
| `rules` | No | [] | Validation rules to apply |

## Built-in Rule Types

### completeness
Check for null values in required columns.

```yaml
- type: completeness
  params:
    required_columns: ["col_a", "col_b"]
    max_null_fraction: 0.01  # allow up to 1% nulls
  severity: error
```

### freshness
Verify data is within recency SLA.

```yaml
- type: freshness
  severity: critical
```

### volume
Check row counts or values against bounds.

```yaml
- type: volume
  params:
    min_count: 1000
    max_count: 10000000
  severity: error
```

### range
Validate all values fall within bounds.

```yaml
- type: range
  params:
    min_value: 0.0
    max_value: 1.0
  severity: critical
```

### distribution
Detect distributional drift via KS or chi-squared tests.

```yaml
- type: distribution
  params:
    method: ks
    p_value_threshold: 0.05
  severity: warning
```

### consistency
Cross-metric coherence checks.

```yaml
- type: consistency
  params:
    relation: sum
    tolerance: 0.01
  severity: error
```

## Dependency Graph

Use `depends_on` to declare that one metric relies on another. metric-guard resolves the dependency graph and validates metrics in topological order, so upstream failures are caught before downstream validation runs.

## Versioning

Bump the `version` field when you change a metric definition. metric-guard records version changes in the audit trail, which is useful when regulators ask "when did the definition of X change?"

## Best Practices

1. **One file per domain**: Group related metrics (e.g., `transparency_metrics.yaml`, `appeals_metrics.yaml`).
2. **Strict freshness on tier-1 metrics**: If a metric appears in external reports, set freshness to `critical`.
3. **Version on every change**: Even small SQL tweaks should bump the patch version.
4. **Tag consistently**: Use tags like `tier-1`, `transparency`, `operational` to filter during validation.
5. **Document the business definition**: Future you will thank present you.
