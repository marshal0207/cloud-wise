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
    DeploymentStatus.QUEUED: {DeploymentStatus.PREPARING, DeploymentStatus.FAILED},
    DeploymentStatus.PREPARING: {DeploymentStatus.BUILDING, DeploymentStatus.FAILED},
    DeploymentStatus.BUILDING: {DeploymentStatus.DEPLOYING, DeploymentStatus.FAILED},
    DeploymentStatus.DEPLOYING: {DeploymentStatus.HEALTH_CHECK, DeploymentStatus.FAILED},
    DeploymentStatus.HEALTH_CHECK: {DeploymentStatus.RUNNING, DeploymentStatus.FAILED},
    DeploymentStatus.RUNNING: {DeploymentStatus.ROLLING_BACK, DeploymentStatus.FAILED},
    DeploymentStatus.FAILED: {DeploymentStatus.ROLLING_BACK},
    DeploymentStatus.ROLLING_BACK: {DeploymentStatus.ROLLED_BACK, DeploymentStatus.FAILED},
    DeploymentStatus.ROLLED_BACK: set(),  # terminal state
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
