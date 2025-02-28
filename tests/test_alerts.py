"""Tests for alerting backends and escalation."""

from unittest.mock import MagicMock

import pytest

from metric_guard.alerts.backend import Alert, AlertRouter
from metric_guard.alerts.console import ConsoleAlertBackend
from metric_guard.alerts.escalation import EscalationManager, EscalationRule
from metric_guard.registry.metric import Severity


@pytest.fixture
def sample_alert() -> Alert:
    return Alert(
        alert_id="alert-001",
        metric_name="content_violation_rate",
        rule_name="freshness",
        severity=Severity.ERROR,
        message="Data is 18.5h old, exceeds 12h SLA",
    )


class TestAlert:
    def test_dedup_key_auto(self, sample_alert: Alert) -> None:
        assert sample_alert.dedup_key == "content_violation_rate:freshness:error"

    def test_custom_dedup_key(self) -> None:
        alert = Alert(
            alert_id="a1",
            metric_name="test",
            rule_name="test",
            severity=Severity.WARNING,
            message="test",
            dedup_key="custom-key",
        )
        assert alert.dedup_key == "custom-key"


class TestConsoleBackend:
    def test_send(self, sample_alert: Alert) -> None:
        from io import StringIO

        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=True)
        backend = ConsoleAlertBackend(console=console)
        result = backend.send(sample_alert)
        assert result is True
        assert len(output.getvalue()) > 0

    def test_connection(self) -> None:
        backend = ConsoleAlertBackend()
        assert backend.test_connection() is True


class TestAlertRouter:
    def test_dedup_suppresses_repeat(self, sample_alert: Alert) -> None:
        mock_backend = MagicMock()
        mock_backend.send.return_value = True
        router = AlertRouter(backends=[mock_backend])

        results1 = router.send(sample_alert)
        assert len(results1) == 1

        # Same alert again -- should be suppressed
        results2 = router.send(sample_alert)
        assert len(results2) == 0

    def test_different_alerts_not_suppressed(self) -> None:
        mock_backend = MagicMock()
        mock_backend.send.return_value = True
        router = AlertRouter(backends=[mock_backend])

        alert1 = Alert(
            alert_id="a1",
            metric_name="metric_a",
            rule_name="freshness",
            severity=Severity.ERROR,
            message="stale",
        )
        alert2 = Alert(
            alert_id="a2",
            metric_name="metric_b",
            rule_name="freshness",
            severity=Severity.ERROR,
            message="stale",
        )

        router.send(alert1)
        results = router.send(alert2)
        assert len(results) == 1

    def test_multi_backend(self, sample_alert: Alert) -> None:
        b1, b2 = MagicMock(), MagicMock()
        b1.send.return_value = True
        b2.send.return_value = False
        router = AlertRouter(backends=[b1, b2])
        results = router.send(sample_alert)
        assert results == [True, False]


class TestEscalation:
    def test_track_and_resolve(self, sample_alert: Alert) -> None:
        mgr = EscalationManager()
        mgr.track(sample_alert)
        assert mgr.open_alert_count == 1
        mgr.resolve(sample_alert.dedup_key)
        assert mgr.open_alert_count == 0

    def test_escalation_rule_triggers(self, sample_alert: Alert) -> None:
        mock_backend = MagicMock()
        mock_backend.send.return_value = True

        rule = EscalationRule(
            min_severity=Severity.ERROR,
            after_minutes=0,  # immediate for testing
            escalate_to=mock_backend,
            escalated_severity=Severity.CRITICAL,
        )

        mgr = EscalationManager(rules=[rule])
        mgr.track(sample_alert)
        escalated = mgr.check_escalations()

        assert len(escalated) == 1
        assert escalated[0].severity == Severity.CRITICAL
        mock_backend.send.assert_called_once()

    def test_escalation_only_fires_once(self, sample_alert: Alert) -> None:
        mock_backend = MagicMock()
        mock_backend.send.return_value = True

        rule = EscalationRule(
            min_severity=Severity.ERROR,
            after_minutes=0,
            escalate_to=mock_backend,
        )

        mgr = EscalationManager(rules=[rule])
        mgr.track(sample_alert)
        mgr.check_escalations()
        mgr.check_escalations()  # second call

        assert mock_backend.send.call_count == 1

    def test_severity_filter(self) -> None:
        mock_backend = MagicMock()

        rule = EscalationRule(
            min_severity=Severity.CRITICAL,
            after_minutes=0,
            escalate_to=mock_backend,
        )

        mgr = EscalationManager(rules=[rule])
        warning_alert = Alert(
            alert_id="w1",
            metric_name="test",
            rule_name="test",
            severity=Severity.WARNING,
            message="just a warning",
        )
        mgr.track(warning_alert)
        escalated = mgr.check_escalations()
        assert len(escalated) == 0
