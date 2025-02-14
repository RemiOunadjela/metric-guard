"""Cron-based scheduling for pulse validation runs."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any

from croniter import croniter

logger = logging.getLogger(__name__)


class PulseScheduler:
    """Schedule periodic validation runs using cron expressions.

    This is intentionally simple -- for production use, you'd likely
    wrap this in a systemd service or Kubernetes CronJob. The scheduler
    handles the timing; the actual validation logic lives elsewhere.
    """

    def __init__(self) -> None:
        self._jobs: list[dict[str, Any]] = []
        self._running = False

    def add_job(
        self,
        name: str,
        cron_expr: str,
        callback: Callable[[], Any],
    ) -> None:
        """Register a job with a cron schedule.

        Args:
            name: Human-readable job identifier.
            cron_expr: Standard cron expression (e.g., ``0 */6 * * *``).
            callback: Function to invoke on each trigger.
        """
        if not croniter.is_valid(cron_expr):
            raise ValueError(f"Invalid cron expression: {cron_expr}")

        self._jobs.append({
            "name": name,
            "cron_expr": cron_expr,
            "callback": callback,
            "cron": croniter(cron_expr, datetime.utcnow()),
            "next_run": None,
        })
        # Compute initial next_run
        self._jobs[-1]["next_run"] = self._jobs[-1]["cron"].get_next(datetime)
        logger.info("Scheduled job '%s' with cron '%s'", name, cron_expr)

    def get_next_runs(self) -> list[dict[str, Any]]:
        """Return the next scheduled run time for each job."""
        return [
            {"name": job["name"], "next_run": job["next_run"], "cron": job["cron_expr"]}
            for job in self._jobs
        ]

    def run_once(self) -> list[dict[str, Any]]:
        """Execute all jobs that are due and return results."""
        now = datetime.utcnow()
        results: list[dict[str, Any]] = []

        for job in self._jobs:
            if job["next_run"] is not None and now >= job["next_run"]:
                logger.info("Executing job '%s'", job["name"])
                try:
                    result = job["callback"]()
                    results.append({
                        "name": job["name"],
                        "status": "success",
                        "result": result,
                        "executed_at": now.isoformat(),
                    })
                except Exception as exc:
                    logger.exception("Job '%s' failed", job["name"])
                    results.append({
                        "name": job["name"],
                        "status": "error",
                        "error": str(exc),
                        "executed_at": now.isoformat(),
                    })
                job["next_run"] = job["cron"].get_next(datetime)

        return results

    def run(self, max_iterations: int | None = None) -> None:
        """Start the scheduler loop.

        Args:
            max_iterations: Stop after this many iterations (for testing).
                            None means run indefinitely.
        """
        self._running = True
        iteration = 0

        while self._running:
            self.run_once()
            iteration += 1
            if max_iterations is not None and iteration >= max_iterations:
                break
            time.sleep(1)

    def stop(self) -> None:
        self._running = False
