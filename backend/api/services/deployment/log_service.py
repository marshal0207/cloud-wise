"""
Structured log service for CloudWise deployments.

Log entries have a fixed schema so the frontend can render them
consistently regardless of which deployment provider produced them.

Schema
------
{
    "timestamp": "<ISO-8601 UTC>",
    "level":     "INFO" | "WARNING" | "ERROR",
    "stage":     <DeploymentStage constant>,
    "message":   "<human-readable text>"
}

Rules
-----
- Entries MUST NOT contain AWS credentials, GitHub tokens,
  passwords, private keys, or any other secrets.
- The ``timestamp`` field is always UTC ISO-8601.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Literal

from .status import DeploymentStage

logger = logging.getLogger(__name__)

LogLevel = Literal["INFO", "WARNING", "ERROR"]


def make_log_entry(
    stage: str,
    message: str,
    level: LogLevel = "INFO",
    timestamp: str | None = None,
) -> dict[str, str]:
    """
    Build a single structured log entry.

    Args:
        stage:     One of the DeploymentStage constants.
        message:   Human-readable description of the event.
        level:     Severity — INFO, WARNING, or ERROR.
        timestamp: ISO-8601 UTC string. If omitted, uses current UTC time.

    Returns:
        Dict with keys: timestamp, level, stage, message.

    Raises:
        ValueError: If stage or level is not a recognised constant.
    """
    if stage not in DeploymentStage.ALL:
        raise ValueError(
            f"Unknown stage '{stage}'. Must be one of {DeploymentStage.ALL}."
        )
    if level not in ("INFO", "WARNING", "ERROR"):
        raise ValueError(
            f"Unknown level '{level}'. Must be INFO, WARNING, or ERROR."
        )

    ts = timestamp or datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "timestamp": ts,
        "level": level,
        "stage": stage,
        "message": message,
    }


class DeploymentLogService:
    """
    Manages an in-memory log buffer for a single deployment session.

    An optional ``listener`` is invoked for every entry as it is written,
    which lets a long-running pipeline stream structured logs to a
    DeploymentRecord in real time instead of only at the end.

    Usage::

        log_svc = DeploymentLogService(deployment_id="dep_abc123")
        log_svc.info(DeploymentStage.BUILDING, "Docker image build started")
        entries = log_svc.all()
    """

    def __init__(
        self,
        deployment_id: str,
        listener=None,
    ) -> None:
        self.deployment_id = deployment_id
        self._entries: list[dict[str, str]] = []
        self._listener = listener

    def _emit(self, entry: dict[str, str]) -> None:
        self._entries.append(entry)
        if self._listener is None:
            return
        try:
            self._listener(entry)
        except Exception:  # noqa: BLE001 — a listener must never break a deploy
            logger.exception("Deployment log listener failed for %s", self.deployment_id)

    # ------------------------------------------------------------------
    # Convenience writers
    # ------------------------------------------------------------------

    def info(self, stage: str, message: str) -> None:
        self._emit(make_log_entry(stage, message, level="INFO"))

    def warning(self, stage: str, message: str) -> None:
        self._emit(make_log_entry(stage, message, level="WARNING"))

    def error(self, stage: str, message: str) -> None:
        self._emit(make_log_entry(stage, message, level="ERROR"))

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def all(self) -> list[dict[str, str]]:
        """Return a copy of all log entries in chronological order."""
        return list(self._entries)

    def by_stage(self, stage: str) -> list[dict[str, str]]:
        """Return entries filtered to a specific stage."""
        return [e for e in self._entries if e["stage"] == stage]

    def count(self) -> int:
        return len(self._entries)

    def clear(self) -> None:
        self._entries.clear()
