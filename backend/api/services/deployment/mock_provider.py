"""
MockDeploymentProvider — Simulated deployment provider.

This provider NEVER:
  - Calls AWS, Azure, GCP, or DigitalOcean APIs
  - Creates real cloud resources
  - Uses or exposes AWS/cloud credentials
  - Stores GitHub tokens or passwords
  - Claim that simulated results represent a real running service

All results are clearly labelled as simulated / mock.

provider_type = "MOCK"
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from .log_service import DeploymentLogService, make_log_entry
from .provider import DeploymentProvider
from .status import DeploymentStage, DeploymentStatus


class UnsupportedProviderError(Exception):
    """Raised when an unsupported provider type is requested."""


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_deployment_id() -> str:
    return f"mock_{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------------------
# In-memory store (process-lifetime; sufficient for tests and demo sessions)
# ---------------------------------------------------------------------------

_store: dict[str, dict[str, Any]] = {}


class MockDeploymentProvider(DeploymentProvider):
    """
    Simulated deployment provider for CloudWise.

    Produces deterministic, structured responses that mirror the lifecycle
    of a real deployment without touching any cloud infrastructure.

    All returned results include ``"simulated": True`` so the frontend
    and tests can assert that no real deployment occurred.
    """

    PROVIDER_TYPE: str = "MOCK"

    # ------------------------------------------------------------------
    # Public interface (DeploymentProvider contract)
    # ------------------------------------------------------------------

    def start(self, configuration: dict[str, Any]) -> dict[str, Any]:
        """
        Register a new mock deployment and return its initial state.

        Args:
            configuration: Must include at minimum:
                             - environment_name (str)
                             - provider (str)  — will be overridden to MOCK
                           Any other keys are stored as-is for later retrieval.

        Returns:
            Initial deployment state dict.

        Raises:
            ValueError: If configuration is missing required keys.
            UnsupportedProviderError: If a non-MOCK provider is explicitly
                                      requested and strict mode is enabled.
        """
        if not configuration.get("environment_name"):
            raise ValueError("configuration must include 'environment_name'.")

        # Allow Vercel, Render, AWS, Azure, GCP, DigitalOcean, and MOCK
        requested_provider = str(configuration.get("provider", "MOCK")).upper()
        allowed_providers = ("MOCK", "VERCEL", "RENDER", "AWS", "AZURE", "GCP", "DIGITALOCEAN", "", "NONE")
        if requested_provider not in allowed_providers:
            raise UnsupportedProviderError(
                f"Provider '{requested_provider}' is not supported. "
                f"Supported providers: {', '.join(allowed_providers)}."
            )

        deployment_id = _make_deployment_id()
        log_svc = DeploymentLogService(deployment_id)

        log_svc.info(
            DeploymentStage.PREPARING,
            "[SIMULATED] Mock deployment initialised — no cloud resources created.",
        )
        log_svc.info(
            DeploymentStage.PREPARING,
            f"[SIMULATED] Environment: {configuration['environment_name']}",
        )

        state: dict[str, Any] = {
            "deployment_id": deployment_id,
            "status": DeploymentStatus.QUEUED,
            "progress": 0,
            "provider_type": self.PROVIDER_TYPE,
            "ip_address": None,
            "endpoint_url": None,
            "configuration": {
                k: v
                for k, v in configuration.items()
                # Strip any accidental secret-like keys
                if k.lower() not in (
                    "token", "secret", "password", "key", "credential",
                    "access_key", "secret_key", "aws_access_key_id",
                    "aws_secret_access_key", "github_token",
                )
            },
            "logs": log_svc.all(),
            "simulated": True,
            "created_at": _utc_now(),
        }

        _store[deployment_id] = {**state, "_log_svc": log_svc}
        return _without_private(state)

    def get_status(self, deployment_id: str) -> dict[str, Any]:
        """
        Return the current mock status for a deployment.

        Advances the deployment through its lifecycle on each call,
        simulating a real progression:
          QUEUED → PREPARING → BUILDING → DEPLOYING → HEALTH_CHECK → RUNNING

        Args:
            deployment_id: ID returned by start().

        Returns:
            Status dict.

        Raises:
            KeyError: If deployment_id is not found in the mock store.
        """
        state = _get_state(deployment_id)
        _advance_mock_state(state)

        return {
            "deployment_id": deployment_id,
            "status": state["status"],
            "progress": state["progress"],
            "provider_type": self.PROVIDER_TYPE,
            "ip_address": state.get("ip_address"),
            "endpoint_url": state.get("endpoint_url"),
            "simulated": True,
            "message": _status_message(state["status"]),
        }

    def get_logs(self, deployment_id: str) -> list[dict[str, Any]]:
        """
        Return structured logs for a mock deployment.

        Logs are guaranteed to contain no secrets, tokens, or credentials.

        Args:
            deployment_id: ID returned by start().

        Returns:
            List of log-entry dicts.
        """
        state = _get_state(deployment_id)
        log_svc: DeploymentLogService = state["_log_svc"]
        return log_svc.all()

    def health_check(self, deployment_id: str) -> dict[str, Any]:
        """
        Simulate a health check for a mock deployment.

        This method never contacts a real server. Results are clearly
        labelled as simulated.

        Args:
            deployment_id: ID returned by start().

        Returns:
            Health-check result dict.
        """
        state = _get_state(deployment_id)
        log_svc: DeploymentLogService = state["_log_svc"]

        log_svc.info(
            DeploymentStage.HEALTH_CHECK,
            "[SIMULATED] Health check initiated — no real server contacted.",
        )
        log_svc.info(
            DeploymentStage.HEALTH_CHECK,
            "[SIMULATED] Mock health check passed — service is responding (simulated).",
        )

        state["status"] = DeploymentStatus.RUNNING
        state["progress"] = 100

        return {
            "deployment_id": deployment_id,
            "healthy": True,
            "provider_type": self.PROVIDER_TYPE,
            "simulated": True,
            "message": (
                "[SIMULATED] Health check passed. "
                "This is a mock result — no real service was checked."
            ),
            "detail": {
                "http_status": None,
                "latency_ms": None,
                "note": "Mock health check — no real HTTP request was made.",
            },
        }

    def fail(self, deployment_id: str, reason: str = "Simulated quota exceeded in target region.") -> dict[str, Any]:
        """
        Force a mock deployment into FAILED state.

        Used by the frontend "Test Simulated Quota Failure" button.
        No real cloud resources are affected.
        """
        state = _get_state(deployment_id)
        log_svc: DeploymentLogService = state["_log_svc"]

        log_svc.error(
            DeploymentStage.FAILED,
            f"[SIMULATED] ERROR: {reason}",
        )
        log_svc.error(
            DeploymentStage.FAILED,
            "[SIMULATED] Deployment halted. Rollback option available.",
        )

        state["status"] = DeploymentStatus.FAILED
        state["progress"] = 45

        return {
            "deployment_id": deployment_id,
            "status": DeploymentStatus.FAILED,
            "provider_type": self.PROVIDER_TYPE,
            "simulated": True,
            "message": f"[SIMULATED] {reason}",
        }

    def rollback(self, deployment_id: str) -> dict[str, Any]:
        """
        Simulate a rollback for a mock deployment.

        Resets the mock deployment state and appends rollback log entries.
        No real infrastructure is modified.

        Args:
            deployment_id: ID returned by start().

        Returns:
            Rollback result dict.
        """
        state = _get_state(deployment_id)
        log_svc: DeploymentLogService = state["_log_svc"]

        log_svc.info(
            DeploymentStage.ROLLBACK,
            "[SIMULATED] Rollback initiated — no cloud resources were modified.",
        )
        log_svc.info(
            DeploymentStage.ROLLBACK,
            "[SIMULATED] Reverting to previous mock deployment state.",
        )
        log_svc.info(
            DeploymentStage.ROLLBACK,
            "[SIMULATED] Mock rollback completed successfully.",
        )

        state["status"] = DeploymentStatus.ROLLED_BACK
        state["progress"] = 0

        return {
            "deployment_id": deployment_id,
            "status": DeploymentStatus.ROLLED_BACK,
            "provider_type": self.PROVIDER_TYPE,
            "simulated": True,
            "message": (
                "[SIMULATED] Rollback completed. "
                "This is a mock result — no real infrastructure was modified."
            ),
            "logs": log_svc.by_stage(DeploymentStage.ROLLBACK),
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_state(deployment_id: str) -> dict[str, Any]:
    """Retrieve deployment state or raise KeyError."""
    state = _store.get(deployment_id)
    if state is None:
        raise KeyError(
            f"Deployment '{deployment_id}' not found in mock store. "
            "Call start() first."
        )
    return state


def _without_private(state: dict[str, Any]) -> dict[str, Any]:
    """Strip internal private keys (prefixed with _) from a state dict."""
    return {k: v for k, v in state.items() if not k.startswith("_")}


# ---------------------------------------------------------------------------
# Mock lifecycle progression
# ---------------------------------------------------------------------------

_LIFECYCLE: list[tuple[str, int, str, str]] = [
    # (status, progress, stage, message)
    (
        DeploymentStatus.PREPARING,
        10,
        DeploymentStage.PREPARING,
        "[SIMULATED] Pulling source repository and preparing build context.",
    ),
    (
        DeploymentStatus.BUILDING,
        35,
        DeploymentStage.BUILDING,
        "[SIMULATED] Docker image build started.",
    ),
    (
        DeploymentStatus.BUILDING,
        60,
        DeploymentStage.BUILDING,
        "[SIMULATED] Docker image built successfully.",
    ),
    (
        DeploymentStatus.DEPLOYING,
        75,
        DeploymentStage.DEPLOYING,
        "[SIMULATED] Starting container and configuring network.",
    ),
    (
        DeploymentStatus.HEALTH_CHECK,
        90,
        DeploymentStage.HEALTH_CHECK,
        "[SIMULATED] Running post-deploy health checks.",
    ),
    (
        DeploymentStatus.RUNNING,
        100,
        DeploymentStage.COMPLETED,
        "[SIMULATED] Deployment complete — mock endpoint is available.",
    ),
]

def _advance_mock_state(state: dict[str, Any]) -> None:
    """
    Advance the mock deployment one step forward in its lifecycle.

    Uses a sequential step counter (_step) stored in the state dict so
    that repeated status names in _LIFECYCLE (e.g. BUILDING appears
    twice) are handled correctly.

    FAILED / ROLLED_BACK / ROLLING_BACK states are terminal and will
    not be automatically advanced.
    """
    current = state["status"]
    if current in (
        DeploymentStatus.RUNNING,
        DeploymentStatus.FAILED,
        DeploymentStatus.ROLLING_BACK,
        DeploymentStatus.ROLLED_BACK,
    ):
        return  # Terminal or already live

    step = state.get("_step", 0)
    if step >= len(_LIFECYCLE):
        return

    next_status, next_progress, stage, message = _LIFECYCLE[step]
    state["status"] = next_status
    state["progress"] = next_progress
    state["_step"] = step + 1

    # Assign mock IP and endpoint when deployment goes live
    if next_status == DeploymentStatus.RUNNING:
        import random as _random
        config = state.get("configuration", {})
        env = config.get("environment_name", "cloudwise-app")
        provider = str(config.get("provider", "MOCK")).upper()
        env_slug = env.lower().replace(' ', '-')
        
        state["ip_address"] = f"35.{_random.randint(10,210)}.{_random.randint(0,255)}.{_random.randint(0,255)}"
        if provider == "VERCEL":
            state["endpoint_url"] = f"https://{env_slug}.vercel.app"
        elif provider == "RENDER":
            state["endpoint_url"] = f"https://{env_slug}.onrender.com"
        else:
            state["endpoint_url"] = f"https://{env_slug}.cloudwise.app"

    log_svc: DeploymentLogService = state["_log_svc"]
    log_svc.info(stage, message)


def _status_message(status: str) -> str:
    messages = {
        DeploymentStatus.QUEUED: "Deployment queued — waiting to start.",
        DeploymentStatus.PREPARING: "Preparing build context.",
        DeploymentStatus.BUILDING: "Building Docker image.",
        DeploymentStatus.DEPLOYING: "Deploying container.",
        DeploymentStatus.HEALTH_CHECK: "Running health checks.",
        DeploymentStatus.RUNNING: "[SIMULATED] Deployment is running.",
        DeploymentStatus.FAILED: "Deployment failed.",
        DeploymentStatus.ROLLING_BACK: "Rolling back deployment.",
        DeploymentStatus.ROLLED_BACK: "[SIMULATED] Rollback completed.",
    }
    return messages.get(status, "Unknown status.")


def clear_mock_store() -> None:
    """
    Clear the in-memory mock deployment store.

    Intended for use in tests only.
    """
    _store.clear()
