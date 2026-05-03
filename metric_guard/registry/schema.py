"""JSON schema for metric definition YAML files."""

METRIC_SCHEMA: dict = {
    "type": "object",
    "required": ["name"],
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "display_name": {"type": "string"},
        "owner": {"type": "string"},
        "business_definition": {"type": "string"},
        "sql_reference": {"type": "string"},
        "update_frequency": {
            "type": "string",
            "enum": ["hourly", "daily", "weekly", "monthly", "quarterly"],
        },
        "sla_hours": {"type": "number", "minimum": 0},
        "tags": {"type": "array", "items": {"type": "string"}},
        "depends_on": {"type": "array", "items": {"type": "string"}},
        "version": {"type": "string"},
        "rules": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["type"],
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": [
                            "completeness",
                            "freshness",
                            "volume",
                            "range",
                            "distribution",
                            "consistency",
                            "monotonicity",
                            "custom",
                        ],
                    },
                    "params": {"type": "object"},
                    "severity": {
                        "type": "string",
                        "enum": ["warning", "error", "critical"],
                    },
                },
            },
        },
        "metadata": {"type": "object"},
    },
}
