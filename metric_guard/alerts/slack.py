"""Slack webhook alert backend."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from metric_guard.alerts.backend import Alert, AlertBackend
from metric_guard.registry.metric import Severity

logger = logging.getLogger(__name__)

_SEVERITY_EMOJI = {
    Severity.WARNING: ":warning:",
    Severity.ERROR: ":x:",
    Severity.CRITICAL: ":rotating_light:",
}


class SlackAlertBackend(AlertBackend):
    """Send alerts to a Slack channel via incoming webhook.

    Uses urllib directly to avoid requiring ``requests`` as a hard dependency.
    """

    def __init__(self, webhook_url: str, channel: str | None = None) -> None:
        self.webhook_url = webhook_url
        self.channel = channel

    def send(self, alert: Alert) -> bool:
        emoji = _SEVERITY_EMOJI.get(alert.severity, ":question:")
        payload = self._build_payload(alert, emoji)

        try:
            req = urllib.request.Request(
                self.webhook_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 200
        except (urllib.error.URLError, urllib.error.HTTPError) as exc:
            logger.error("Failed to send Slack alert: %s", exc)
            return False

    def test_connection(self) -> bool:
        payload = {"text": "metric-guard test alert -- please ignore."}
        try:
            req = urllib.request.Request(
                self.webhook_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 200
        except Exception:
            return False

    def _build_payload(self, alert: Alert, emoji: str) -> dict[str, Any]:
        blocks: list[dict[str, Any]] = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} {alert.severity.value.upper()}: {alert.metric_name}",
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Rule:*\n{alert.rule_name}"},
                    {"type": "mrkdwn", "text": f"*Severity:*\n{alert.severity.value}"},
                ],
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": alert.message},
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Alert ID: `{alert.alert_id}` | "
                        f"{alert.created_at.strftime('%Y-%m-%d %H:%M UTC')}",
                    }
                ],
            },
        ]

        payload: dict[str, Any] = {"blocks": blocks}
        if self.channel:
            payload["channel"] = self.channel
        return payload
