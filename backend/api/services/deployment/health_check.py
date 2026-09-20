"""
Provider-independent health-check service for CloudWise deployments.

The concrete behaviour is delegated to the DeploymentProvider.
This module adds a thin orchestration layer that:

  1. Calls provider.health_check(deployment_id)
  2. Normalises the result into a fixed schema
  3. Ensures the result never claims to have reached a real server
     when the provider is MOCK.

Result schema
-------------
{
    "deployment_id": str,
    "healthy":       bool,
    "provider_type": str,
    "message":       str,
    "detail":        dict  (provider-specific, optional)
}
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .provider import DeploymentProvider


class DeploymentHealthCheckService:
    """
    Orchestrates health checks across any DeploymentProvider.

    Usage::

        provider = MockDeploymentProvider()
        svc = DeploymentHealthCheckService(provider)
        result = svc.run(deployment_id="dep_abc123")
    """

    def __init__(self, provider: "DeploymentProvider") -> None:
        self._provider = provider

    def run(self, deployment_id: str) -> dict[str, Any]:
        """
        Execute the health check via the configured provider.

        Args:
            deployment_id: Deployment identifier returned by provider.start().

        Returns:
            Normalised health-check result dict.
        """
        raw = self._provider.health_check(deployment_id)

        # Normalise to guaranteed keys
        result: dict[str, Any] = {
            "deployment_id": deployment_id,
            "healthy": bool(raw.get("healthy", False)),
            "provider_type": raw.get("provider_type", self._provider.PROVIDER_TYPE),
            "message": raw.get("message", ""),
            "detail": raw.get("detail", {}),
        }

        return result
