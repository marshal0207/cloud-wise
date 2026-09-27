"""
Deployment status constants and valid state-transition rules.

Uses plain string constants (not Django model choices) so this module
can be imported in tests without any Django setup.

Statuses
--------
QUEUED        — Deployment request received, not yet started.
PREPARING     — Pulling source, preparing build context.
BUILDING      — Building the Docker image.
DEPLOYING     — Starting container / pushing to registry.
HEALTH_CHECK  — Running post-deploy health checks.
RUNNING       — Deployment is live and healthy.
FAILED        — Deployment encountered an unrecoverable error.
ROLLING_BACK  — Rollback is in progress.
ROLLED_BACK   — Rollback completed successfully.
TERMINATED    — The EC2 instance was terminated by its owner.
"""

from __future__ import annotations


class DeploymentStatus:
    QUEUED = "QUEUED"
    PREPARING = "PREPARING"
    BUILDING = "BUILDING"
    DEPLOYING = "DEPLOYING"
    HEALTH_CHECK = "HEALTH_CHECK"
    RUNNING = "RUNNING"
    FAILED = "FAILED"
    ROLLING_BACK = "ROLLING_BACK"
    ROLLED_BACK = "ROLLED_BACK"
    TERMINATED = "TERMINATED"

    ALL: tuple[str, ...] = (
        QUEUED,
        PREPARING,
        BUILDING,
        DEPLOYING,
        HEALTH_CHECK,
        RUNNING,
        FAILED,
        ROLLING_BACK,
        ROLLED_BACK,
        TERMINATED,
    )


class DeploymentStage:
    """Log stage labels — used in structured log entries."""

    PREPARING = "PREPARING"
    BUILDING = "BUILDING"
    DEPLOYING = "DEPLOYING"
    HEALTH_CHECK = "HEALTH_CHECK"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ROLLBACK = "ROLLBACK"

    ALL: tuple[str, ...] = (
        PREPARING,
        BUILDING,
        DEPLOYING,
        HEALTH_CHECK,
        COMPLETED,
        FAILED,
        ROLLBACK,
    )


# ---------------------------------------------------------------------------
# Valid state-machine transitions
# ---------------------------------------------------------------------------

_VALID_TRANSITIONS: dict[str, set[str]] = {
    # Every non-terminal state may be stopped by the user (Part 14).
    DeploymentStatus.QUEUED: {
        DeploymentStatus.PREPARING,
        DeploymentStatus.FAILED,
        DeploymentStatus.TERMINATED,
    },
    DeploymentStatus.PREPARING: {
        DeploymentStatus.BUILDING,
        DeploymentStatus.FAILED,
        DeploymentStatus.TERMINATED,
    },
    DeploymentStatus.BUILDING: {
        DeploymentStatus.DEPLOYING,
        DeploymentStatus.FAILED,
        DeploymentStatus.TERMINATED,
    },
    DeploymentStatus.DEPLOYING: {
        DeploymentStatus.HEALTH_CHECK,
        DeploymentStatus.FAILED,
        DeploymentStatus.TERMINATED,
    },
    DeploymentStatus.HEALTH_CHECK: {
        DeploymentStatus.RUNNING,
        DeploymentStatus.FAILED,
        DeploymentStatus.TERMINATED,
    },
    DeploymentStatus.RUNNING: {
        DeploymentStatus.ROLLING_BACK,
        DeploymentStatus.FAILED,
        DeploymentStatus.TERMINATED,
    },
    DeploymentStatus.FAILED: {
        DeploymentStatus.ROLLING_BACK,
        DeploymentStatus.QUEUED,  # retry restarts the pipeline on the record
        DeploymentStatus.TERMINATED,
    },
    DeploymentStatus.ROLLING_BACK: {
        DeploymentStatus.ROLLED_BACK,
        DeploymentStatus.FAILED,
        DeploymentStatus.TERMINATED,
    },
    DeploymentStatus.ROLLED_BACK: {
        DeploymentStatus.QUEUED,  # retry after a rollback
        DeploymentStatus.TERMINATED,
    },
    DeploymentStatus.TERMINATED: set(),  # terminal state
}


def is_valid_transition(from_status: str, to_status: str) -> bool:
    """
    Return True if the status transition from → to is permitted.

    Args:
        from_status: Current deployment status.
        to_status:   Desired next deployment status.

    Returns:
        True if the transition is allowed, False otherwise.
    """
    allowed = _VALID_TRANSITIONS.get(from_status, set())
    return to_status in allowed


def get_allowed_transitions(status: str) -> frozenset[str]:
    """Return all statuses reachable from the given status."""
    return frozenset(_VALID_TRANSITIONS.get(status, set()))


class InvalidTransition(Exception):
    """Raised when a caller attempts a status change that is not allowed."""

    def __init__(self, from_status: str, to_status: str):
        self.from_status = from_status
        self.to_status = to_status
        allowed = ", ".join(sorted(_VALID_TRANSITIONS.get(from_status, set()))) or "none"
        super().__init__(
            f"Invalid deployment transition {from_status} → {to_status}. "
            f"Allowed from {from_status}: {allowed}."
        )


def transition_to(from_status: str, to_status: str) -> str:
    """
    Validate and return the target status.

    Raises InvalidTransition when the change is not permitted by the
    state machine, so no code path can silently jump QUEUED → RUNNING.
    """
    if not is_valid_transition(from_status, to_status):
        raise InvalidTransition(from_status, to_status)
    return to_status


# ---------------------------------------------------------------------------
# Derived values — one place for progress/stage so the API, the pipeline
# and the frontend can never disagree about what a status means.
# ---------------------------------------------------------------------------

# Deterministic progress derived from the real status. There are no timers
# and no fabricated intermediate percentages.
STATUS_PROGRESS: dict[str, int] = {
    DeploymentStatus.QUEUED: 5,
    DeploymentStatus.PREPARING: 15,
    DeploymentStatus.BUILDING: 45,
    DeploymentStatus.DEPLOYING: 70,
    DeploymentStatus.HEALTH_CHECK: 90,
    DeploymentStatus.RUNNING: 100,
    DeploymentStatus.FAILED: 60,
    DeploymentStatus.ROLLING_BACK: 50,
    DeploymentStatus.ROLLED_BACK: 100,
    DeploymentStatus.TERMINATED: 100,
    # legacy lowercase records created before migration 0007
    "deployed": 100,
    "deploying": 45,
    "failed": 60,
}

# Statuses owned by a running pipeline (or an in-progress rollback).
IN_FLIGHT: tuple[str, ...] = (
    DeploymentStatus.QUEUED,
    DeploymentStatus.PREPARING,
    DeploymentStatus.BUILDING,
    DeploymentStatus.DEPLOYING,
    DeploymentStatus.HEALTH_CHECK,
    DeploymentStatus.ROLLING_BACK,
)

# Statuses no pipeline is running for.
SETTLED: tuple[str, ...] = (
    DeploymentStatus.RUNNING,
    DeploymentStatus.FAILED,
    DeploymentStatus.ROLLED_BACK,
    DeploymentStatus.TERMINATED,
)


def is_in_flight(status: str) -> bool:
    """True while a background pipeline still owns this deployment."""
    return status in IN_FLIGHT


def is_settled(status: str) -> bool:
    """True when no pipeline work is outstanding for this status."""
    return status in SETTLED


def progress_for(status: str) -> int:
    """Deterministic 0–100 progress for a deployment status."""
    return STATUS_PROGRESS.get(status, 0)


def default_error_code(status: str) -> str:
    """Stable machine-readable code for a failed deployment."""
    return f"DEPLOYMENT_{status}" if status else "DEPLOYMENT_FAILED"
