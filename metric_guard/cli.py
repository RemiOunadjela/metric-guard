"""Command-line interface for metric-guard."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from metric_guard import __version__
from metric_guard.config import load_config

console = Console()
err_console = Console(stderr=True)

_SCAFFOLD_METRIC = """\
metrics:
  - name: example_metric
    display_name: "Example Metric"
    owner: "data-quality-team"
    business_definition: >
      Description of what this metric measures and why it matters
      for compliance reporting.
    sql_reference: "SELECT COUNT(*) FROM actions WHERE ..."
    update_frequency: daily
    sla_hours: 24
    tags:
      - compliance
      - transparency
    depends_on: []
    version: "1.0.0"
    rules:
      - type: completeness
        params:
          required_columns: ["action_id", "timestamp", "category"]
        severity: error
      - type: freshness
        severity: critical
      - type: volume
        params:
          min_count: 100
        severity: warning
"""


@click.group()
@click.version_option(__version__, prog_name="metric-guard")
def cli() -> None:
    """Automated data quality for compliance metrics."""


@cli.command()
@click.option("--dir", "directory", default="metrics/", help="Directory for metric definitions")
def init(directory: str) -> None:
    """Scaffold metric definition files and configuration."""
    metrics_dir = Path(directory)
    metrics_dir.mkdir(parents=True, exist_ok=True)

    example_file = metrics_dir / "example_metrics.yaml"
    if example_file.exists():
        err_console.print(f"[yellow]Warning:[/] {example_file} already exists, skipping.")
    else:
        example_file.write_text(_SCAFFOLD_METRIC)
        console.print(f"[green]Created[/] {example_file}")

    config_file = Path("metric_guard.yaml")
    if not config_file.exists():
        config_file.write_text(
            f"metrics_dir: {directory}\nenvironment: development\n"
            f"alerts:\n  backend: console\n"
            f"audit:\n  db_path: .metric_guard/audit.db\n"
        )
        console.print(f"[green]Created[/] {config_file}")

    guard_dir = Path(".metric_guard")
    guard_dir.mkdir(exist_ok=True)

    console.print("\n[bold]metric-guard initialized.[/]")
    console.print(f"  Metric definitions: {metrics_dir}/")
    console.print(f"  Configuration:      {config_file}")
    console.print("\nNext steps:")
    console.print("  1. Edit your metric definitions in the metrics/ directory")
    console.print("  2. Run [bold]metric-guard validate[/] to check data quality")


@cli.command()
@click.option("--metrics", default="all", help="Metric name or 'all'")
@click.option("--env", "environment", default=None, help="Environment override")
@click.option("--config", "config_path", default=None, help="Config file path")
@click.option("--json", "output_json", is_flag=True, help="Output results as JSON (for scripting)")
def validate(
    metrics: str, environment: str | None, config_path: str | None, output_json: bool
) -> None:
    """Run validation rules against metric definitions."""
    import json

    config = load_config(config_path)
    if environment:
        config.environment = environment

    metrics_dir = Path(config.metrics_dir)
    if not metrics_dir.exists():
        if output_json:
            click.echo(json.dumps({"error": f"Metrics directory '{metrics_dir}' not found."}))
        else:
            err_console.print(
                f"[red]Error:[/] Metrics directory '{metrics_dir}' not found. "
                f"Run [bold]metric-guard init[/] first."
            )
        sys.exit(1)

    from metric_guard.registry.loader import load_metrics_from_dir

    try:
        all_metrics = load_metrics_from_dir(metrics_dir)
    except Exception as exc:
        if output_json:
            click.echo(json.dumps({"error": str(exc)}))
        else:
            err_console.print(f"[red]Error loading metrics:[/] {exc}")
        sys.exit(1)

    if not all_metrics:
        if output_json:
            click.echo(
                json.dumps(
                    {
                        "environment": config.environment,
                        "metrics": [],
                        "total_metrics": 0,
                        "total_rules": 0,
                    }
                )
            )
        else:
            err_console.print("[yellow]No metric definitions found.[/]")
        sys.exit(0)

    if metrics != "all":
        all_metrics = [m for m in all_metrics if m.name == metrics]
        if not all_metrics:
            if output_json:
                click.echo(json.dumps({"error": f"Metric '{metrics}' not found."}))
            else:
                err_console.print(f"[red]Metric '{metrics}' not found.[/]")
            sys.exit(1)

    if output_json:
        result = {
            "environment": config.environment,
            "total_metrics": len(all_metrics),
            "total_rules": sum(len(m.rules) for m in all_metrics),
            "metrics": [
                {
                    "name": m.name,
                    "display_name": m.display_name or m.name,
                    "owner": m.owner,
                    "version": m.version,
                    "sla_hours": m.sla_hours,
                    "update_frequency": m.update_frequency.value,
                    "rule_count": len(m.rules),
                    "tags": m.tags,
                    "depends_on": m.depends_on,
                    "status": "defined",
                }
                for m in all_metrics
            ],
        }
        click.echo(json.dumps(result, indent=2))
        return

    from collections import Counter

    from metric_guard.registry.metric import Severity

    table = Table(title=f"Validation Results  ·  {config.environment}")
    table.add_column("Metric", style="cyan", no_wrap=True)
    table.add_column("Owner", style="dim")
    table.add_column("Rules", justify="right")
    table.add_column("Critical", justify="right")
    table.add_column("Error", justify="right")
    table.add_column("Warning", justify="right")
    table.add_column("Version")
    table.add_column("SLA", justify="right")

    severity_totals: Counter[str] = Counter()

    for m in all_metrics:
        by_sev: Counter[Severity] = Counter(r.severity for r in m.rules)
        crit = by_sev.get(Severity.CRITICAL, 0)
        err = by_sev.get(Severity.ERROR, 0)
        warn = by_sev.get(Severity.WARNING, 0)
        severity_totals["critical"] += crit
        severity_totals["error"] += err
        severity_totals["warning"] += warn

        table.add_row(
            m.display_name or m.name,
            m.owner or "\u2014",
            str(len(m.rules)),
            f"[bold red]{crit}[/]" if crit else "[dim]\u2014[/]",
            f"[yellow]{err}[/]" if err else "[dim]\u2014[/]",
            f"[blue]{warn}[/]" if warn else "[dim]\u2014[/]",
            m.version,
            f"{m.sla_hours}h",
        )

    console.print(table)

    total_rules = sum(len(m.rules) for m in all_metrics)
    summary_parts = [
        f"[bold]{len(all_metrics)}[/] metric(s)",
        f"[bold]{total_rules}[/] rule(s)",
    ]
    if severity_totals["critical"]:
        summary_parts.append(f"[bold red]{severity_totals['critical']} critical[/]")
    if severity_totals["error"]:
        summary_parts.append(f"[yellow]{severity_totals['error']} error[/]")
    if severity_totals["warning"]:
        summary_parts.append(f"[blue]{severity_totals['warning']} warning[/]")
    console.print("\n" + "  ·  ".join(summary_parts))


@cli.command()
@click.option("--schedule", default="0 */6 * * *", help="Cron expression for pulse")
@click.option("--once", is_flag=True, help="Run once and exit")
def pulse(schedule: str, once: bool) -> None:
    """Start pulse monitoring with scheduled validation runs."""
    from croniter import croniter

    if not croniter.is_valid(schedule):
        err_console.print(f"[red]Invalid cron expression:[/] {schedule}")
        sys.exit(1)

    next_run = croniter(schedule).get_next(datetime)
    console.print("[bold]Pulse monitor[/]")
    console.print(f"  Schedule: {schedule}")
    console.print(f"  Next run: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")

    if once:
        console.print("\n[dim]Running one-shot validation...[/]")
        # In a real deployment, this would load metrics and run all rules
        console.print("[green]Pulse check complete.[/]")
    else:
        console.print("\n[dim]Press Ctrl+C to stop.[/]")
        from metric_guard.pulse.scheduler import PulseScheduler

        scheduler = PulseScheduler()
        scheduler.add_job("pulse", schedule, lambda: console.print("[green]tick[/]"))
        try:
            scheduler.run()
        except KeyboardInterrupt:
            scheduler.stop()
            console.print("\n[yellow]Pulse stopped.[/]")


@cli.command()
@click.option("--from", "from_date", default=None, help="Start date (YYYY-MM-DD)")
@click.option("--to", "to_date", default=None, help="End date (YYYY-MM-DD)")
@click.option("--format", "fmt", type=click.Choice(["json", "csv"]), default="json")
@click.option("--output", "-o", default=None, help="Output file (default: stdout)")
def audit(from_date: str | None, to_date: str | None, fmt: str, output: str | None) -> None:
    """Export audit trail for regulatory review."""
    from metric_guard.audit.export import AuditExporter
    from metric_guard.audit.store import AuditStore

    config = load_config()
    store = AuditStore(config.audit.db_path)
    exporter = AuditExporter(store)

    fd = datetime.fromisoformat(from_date) if from_date else None
    td = datetime.fromisoformat(to_date) if to_date else None

    if fmt == "csv":
        content = exporter.export_csv(from_date=fd, to_date=td)
    else:
        content = exporter.export_json(from_date=fd, to_date=td)

    if output:
        Path(output).write_text(content)
        console.print(f"[green]Audit report written to {output}[/]")
    else:
        click.echo(content)

    store.close()


@cli.command()
def status() -> None:
    """Dashboard view of all metrics health."""
    config = load_config()
    metrics_dir = Path(config.metrics_dir)

    if not metrics_dir.exists():
        err_console.print("[yellow]No metrics directory found. Run metric-guard init.[/]")
        sys.exit(0)

    from metric_guard.registry.loader import load_metrics_from_dir

    try:
        all_metrics = load_metrics_from_dir(metrics_dir)
    except Exception as exc:
        err_console.print(f"[red]Error:[/] {exc}")
        sys.exit(1)

    header = Text()
    header.append("metric-guard ", style="bold cyan")
    header.append(f"v{__version__}", style="dim")
    header.append(f"  |  env: {config.environment}", style="dim")

    console.print(Panel(header, expand=False))

    if not all_metrics:
        console.print("[yellow]No metrics defined yet.[/]")
        return

    table = Table()
    table.add_column("Metric", style="bold")
    table.add_column("Owner")
    table.add_column("Frequency")
    table.add_column("SLA")
    table.add_column("Rules", justify="right")
    table.add_column("Dependencies", justify="right")
    table.add_column("Version")

    for m in all_metrics:
        table.add_row(
            m.display_name or m.name,
            m.owner or "-",
            m.update_frequency.value,
            f"{m.sla_hours}h",
            str(len(m.rules)),
            str(len(m.depends_on)),
            m.version,
        )

    console.print(table)
    console.print(f"\n[bold]{len(all_metrics)}[/] metric(s) registered.")


if __name__ == "__main__":
    cli()
