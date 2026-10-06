"""
EC2 lifecycle guard — separates *deployment success* from *destruction*.

CloudWise's rule: a successful deployment keeps its EC2 instance running
indefinitely. Termination only ever happens through an explicit user
action (Destroy/Delete Deployment).

This module marks the code that runs as part of the background
deployment worker (the pipeline thread). ``AwsEc2Provider`` uses
``in_deployment_worker()`` to refuse any TerminateInstances call that
would originate from that worker, so a generic cleanup/finally handler
added in the future can never destroy a healthy deployment: it is
logged as an error and prevented instead of being executed.
"""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from typing import Iterator

logger = logging.getLogger(__name__)

_worker = threading.local()


def in_deployment_worker() -> bool:
    """True while executing inside the background deployment pipeline."""
    return bool(getattr(_worker, "active", False))


@contextmanager
def deployment_worker() -> Iterator[None]:
    """
    Mark the current thread as running the deployment pipeline.

    Nested use is safe: the previous marker is restored on exit.
    """
    previous = in_deployment_worker()
    _worker.active = True
    try:
        yield
    finally:
        _worker.active = previous


def refusal_message(action: str, detail: str) -> str:
    """Log (as an error) and build the message for a refused action."""
    logger.error("Automatic infrastructure %s refused: %s", action, detail)
    return (
        f"Refusing automatic infrastructure {action}: {detail}. "
        "Destructive EC2 actions are only allowed from an explicit "
        "user action (Stop / Destroy Deployment)."
    )
