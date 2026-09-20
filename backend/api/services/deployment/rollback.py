"""
Provider-independent rollback service for CloudWise deployments.

Delegates the actual rollback operation to the DeploymentProvider and
normalises the result into a fixed schema.

Result schema
-------------
{
    "deployment_id": str,
    "status":        str   — DeploymentStatus.ROLLING_BACK or ROLLED_BACK
    "provider_type": str,
    "message":       str,
    "logs":          list[dict]  — structured rollback log entries
}
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .provider import DeploymentProvider


class DeploymentRollbackService:
    """
    Orchestrates rollback across any DeploymentProvider.

    Usage::

        provider = MockDeploymentProvider()
        svc = DeploymentRollbackService(provider)
        result = svc.run(deployment_id="dep_abc123")
    """

    def __init__(self, provider: "DeploymentProvider") -> None:
        self._provider = provider

    def run(self, deployment_id: str) -> dict[str, Any]:
        """
        Initiate a rollback via the configured provider.

        Args:
            deployment_id: Deployment identifier returned by provider.start().

        Returns:
            Normalised rollback result dict.
        """
        raw = self._provider.rollback(deployment_id)

        result: dict[str, Any] = {
            "deployment_id": deployment_id,
            "status": raw.get("status", "ROLLED_BACK"),
            "provider_type": raw.get("provider_type", self._provider.PROVIDER_TYPE),
            "message": raw.get("message", ""),
            "logs": raw.get("logs", []),
        }

        return result
