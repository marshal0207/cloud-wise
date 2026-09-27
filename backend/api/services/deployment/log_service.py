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
import re
from datetime import datetime, timezone
from typing import Literal

from .status import DeploymentStage

logger = logging.getLogger(__name__)

LogLevel = Literal["INFO", "WARNING", "ERROR"]


# ---------------------------------------------------------------------------
# Secret redaction (Part 25)
#
# Defence in depth: no code path should ever put a credential into a log
# message, but every message still passes through here so an unexpected
# boto3/botocore error string can never persist an AWS key, GitHub token,
# session token or private key in the DeploymentRecord.
# ---------------------------------------------------------------------------

_SECRET_PATTERNS: tuple[tuple[re.Pattern, str], ...] = (
    # AWS access key ids (long-lived and STS temporary)
    (re.compile(r"\b(?:AKIA|ASIA|AIDA|AROA|ANPA|ANVA)[0-9A-Z]{16}\b"), "[REDACTED_AWS_KEY_ID]"),
    # AWS secret access keys / session tokens (40+ base64-ish chars)
    (
        re.compile(
            r"(?i)\b(secret[_-]?access[_-]?key|aws_secret_access_key|session[_-]?token"
            r"|aws_session_token|security[_-]?token|password|passwd|pwd|token|api[_-]?key"
            r"|authorization|private[_-]?key)\b\s*[:=]\s*['\"]?([A-Za-z0-9+/=_\-.]{8,})"
        ),
        r"\1=[REDACTED]",
    ),
    # Bare long credential-looking tokens (session tokens are 100+ chars)
    (re.compile(r"\b[A-Za-z0-9+/=]{100,}\b"), "[REDACTED_LONG_TOKEN]"),
    # GitHub tokens
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"), "[REDACTED_GITHUB_TOKEN]"),
    # PEM private key blocks
    (
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
            re.DOTALL,
        ),
        "[REDACTED_PRIVATE_KEY]",
    ),
    # Basic auth in URLs (postgres://user:pass@host)
    (re.compile(r"(?<=://)([^/\s:@]+):([^/\s@]+)@"), r"\1:[REDACTED]@"),
)


def sanitize_message(message: str) -> str:
    """
    Redact anything that looks like a credential from a log message.

    Returns the message unchanged when it contains no secrets.
    """
    if not message:
        return message
    text = str(message)
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


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
        "message": sanitize_message(message),
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
