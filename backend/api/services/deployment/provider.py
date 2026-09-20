"""
DeploymentProvider — Abstract base class for all deployment providers.

Defines the provider-independent interface that every deployment
backend (Mock, future AWS, Azure, GCP, DigitalOcean) must implement.
No cloud SDK is imported here. No credentials are referenced.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class DeploymentProvider(ABC):
    """
    Abstract deployment provider interface.

    Concrete implementations must never expose cloud credentials,
    tokens, or private keys in return values or logs.
    """

    PROVIDER_TYPE: str = "UNKNOWN"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @abstractmethod
    def start(self, configuration: dict[str, Any]) -> dict[str, Any]:
        """
        Start a new deployment with the given configuration.

        Args:
            configuration: Provider-agnostic deployment configuration dict.
                           Required keys (minimum):
                             - environment_name (str)
                             - provider (str)

        Returns:
            A dict containing at least:
              - deployment_id (str)
              - status (str)  — one of DeploymentStatus values
              - provider_type (str)
              - message (str)
        """

    @abstractmethod
    def get_status(self, deployment_id: str) -> dict[str, Any]:
        """
        Return the current status of a deployment.

        Args:
            deployment_id: Opaque deployment identifier returned by start().

        Returns:
            A dict containing at least:
              - deployment_id (str)
              - status (str)
              - progress (int)  — 0-100
              - provider_type (str)
        """

    @abstractmethod
    def get_logs(self, deployment_id: str) -> list[dict[str, Any]]:
        """
        Retrieve structured logs for a deployment.

        Returns:
            A list of log-entry dicts (see make_log_entry in log_service).
            Must never include secrets, tokens, or credentials.
        """

    @abstractmethod
    def health_check(self, deployment_id: str) -> dict[str, Any]:
        """
        Perform (or simulate) a health check on the deployed service.

        Returns:
            A dict containing at least:
              - deployment_id (str)
              - healthy (bool)
              - provider_type (str)
              - message (str)

        Must never claim that a mock health check reached a real server.
        """

    @abstractmethod
    def rollback(self, deployment_id: str) -> dict[str, Any]:
        """
        Initiate (or simulate) a rollback of the deployment.

        Returns:
            A dict containing at least:
              - deployment_id (str)
              - status (str)
              - provider_type (str)
              - message (str)
        """
