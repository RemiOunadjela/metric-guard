"""Console alert backend using rich for formatted output."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from metric_guard.alerts.backend import Alert, AlertBackend
from metric_guard.registry.metric import Severity

_SEVERITY_STYLES = {
    Severity.WARNING: "yellow",
    Severity.ERROR: "red",
    Severity.CRITICAL: "bold red on white",
}


class ConsoleAlertBackend(AlertBackend):
    """Print alerts to the console with color-coded severity."""

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console(stderr=True)

    def send(self, alert: Alert) -> bool:
        style = _SEVERITY_STYLES.get(alert.severity, "white")

        title = Text()
        title.append(f"[{alert.severity.value.upper()}] ", style=style)
        title.append(alert.metric_name, style="bold")
        title.append(f" / {alert.rule_name}")

        body = Text(alert.message)

        self.console.print(
            Panel(
                body,
                title=str(title),
                border_style=style,
                subtitle=alert.created_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
            )
        )
        return True

    def test_connection(self) -> bool:
        return True
