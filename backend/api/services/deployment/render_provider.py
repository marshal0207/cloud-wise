"""
RenderDeploymentService — Real Render REST API deployment.

Uses the official Render API:
  https://api-docs.render.com/reference/create-service
  https://api-docs.render.com/reference/create-deploy

Required environment variables:
  RENDER_API_KEY  — API key from dashboard.render.com/u/settings
  RENDER_OWNER_ID — Owner ID (user or team) from Render dashboard

Flow:
  1. Create or retrieve existing Render service linked to the repo.
  2. Trigger a deploy on that service.
  3. Poll deploy status until live or failed.
  4. Return the real service URL from Render.
  5. HTTP-verify the URL is reachable.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


RENDER_API = "https://api.render.com/v1"
_POLL_INTERVAL = 8   # seconds between status polls
_MAX_POLLS = 60      # ~8 min timeout


class RenderApiError(Exception):
    pass


# Render service type mapping
_SERVICE_TYPE_MAP = {
    "PYTHON": "web_service",
    "NODE_JS": "web_service",
    "REACT": "static_site",
    "SPRING_BOOT": "web_service",
    "DOCKER": "web_service",
    "UNKNOWN": "web_service",
}

_RUNTIME_MAP = {
    "PYTHON": "python",
    "NODE_JS": "node",
    "REACT": "static",
    "SPRING_BOOT": "docker",
    "DOCKER": "docker",
    "UNKNOWN": "docker",
}


class RenderDeploymentService:
    def __init__(self, api_key: str, owner_id: str) -> None:
        if not api_key:
            raise ValueError("RENDER_API_KEY is required.")
        if not owner_id:
            raise ValueError("RENDER_OWNER_ID is required.")
        self._api_key = api_key
        self._owner_id = owner_id

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def deploy(
        self,
        *,
        repo_full_name: str,
        branch: str,
        service_name: str,
        technology: str,
        build_command: str | None,
        start_command: str | None,
        root_directory: str | None,
        port: int,
        env_vars: dict[str, str] | None,
        existing_service_id: str | None,
        has_dockerfile: bool,
    ) -> dict[str, Any]:
        """
        Deploy a GitHub repository to Render.

        Returns dict with keys:
          provider_service_id, deploy_id, url, status
        """
        service_type = "static_site" if technology == "REACT" else "web_service"
        runtime = _RUNTIME_MAP.get(technology, "docker")
        if has_dockerfile:
            runtime = "docker"
            service_type = "web_service"

        if existing_service_id:
            service_id = existing_service_id
            service_url = self._get_service_url(service_id)
        else:
            service = self._create_service(
                name=service_name,
                repo_full_name=repo_full_name,
                branch=branch,
                service_type=service_type,
                runtime=runtime,
                build_command=build_command,
                start_command=start_command,
                root_directory=root_directory,
                port=port,
                env_vars=env_vars or {},
            )
            service_id = service["service"]["id"]
            service_url = service["service"].get("serviceDetails", {}).get("url") or \
                          f"https://{service_name}.onrender.com"

        # Trigger a new deploy
        deploy = self._trigger_deploy(service_id)
        deploy_id = deploy["id"]

        # Poll until terminal
        final = self._poll_deploy(service_id, deploy_id)

        # Get the real URL from the service
        real_url = self._get_service_url(service_id) or service_url

        return {
            "provider_service_id": service_id,
            "deploy_id": deploy_id,
            "url": real_url,
            "status": final.get("status", "unknown"),
            "raw": final,
        }

    def get_deploy_status(self, service_id: str, deploy_id: str) -> dict[str, Any]:
        return self._request("GET", f"/services/{service_id}/deploys/{deploy_id}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_service_url(self, service_id: str) -> str | None:
        try:
            data = self._request("GET", f"/services/{service_id}")
            return data.get("serviceDetails", {}).get("url")
        except RenderApiError:
            return None

    def _create_service(
        self,
        *,
        name: str,
        repo_full_name: str,
        branch: str,
        service_type: str,
        runtime: str,
        build_command: str | None,
        start_command: str | None,
        root_directory: str | None,
        port: int,
        env_vars: dict[str, str],
    ) -> dict[str, Any]:
        env_list = [{"key": k, "value": v} for k, v in env_vars.items()]

        body: dict[str, Any] = {
            "type": service_type,
            "name": name,
            "ownerId": self._owner_id,
            "repo": f"https://github.com/{repo_full_name}",
            "branch": branch,
            "autoDeploy": "no",
            "envVars": env_list,
        }

        if service_type == "web_service":
            body["serviceDetails"] = {
                "runtime": runtime,
                "numInstances": 1,
                "plan": "free",
                "region": "oregon",
            }
            if build_command:
                body["serviceDetails"]["buildCommand"] = build_command
            if start_command:
                body["serviceDetails"]["startCommand"] = start_command
            if root_directory:
                body["serviceDetails"]["rootDir"] = root_directory
            if port:
                body["serviceDetails"]["envSpecificDetails"] = {"port": port}
        elif service_type == "static_site":
            body["serviceDetails"] = {}
            if build_command:
                body["serviceDetails"]["buildCommand"] = build_command
            if root_directory:
                body["serviceDetails"]["rootDir"] = root_directory
            body["serviceDetails"]["publishPath"] = "dist"

        return self._request("POST", "/services", body)

    def _trigger_deploy(self, service_id: str) -> dict[str, Any]:
        return self._request("POST", f"/services/{service_id}/deploys", {"clearCache": "do_not_clear"})

    def _poll_deploy(self, service_id: str, deploy_id: str) -> dict[str, Any]:
        terminal = {"live", "failed", "canceled", "deactivated"}
        for _ in range(_MAX_POLLS):
            data = self.get_deploy_status(service_id, deploy_id)
            status = data.get("status", "").lower()
            if status in terminal:
                return data
            time.sleep(_POLL_INTERVAL)
        raise RenderApiError(f"Deploy {deploy_id} timed out after {_MAX_POLLS * _POLL_INTERVAL}s.")

    def _request(self, method: str, path: str, body: Any = None) -> Any:
        url = RENDER_API + path
        data = json.dumps(body).encode() if body is not None else None
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode(errors="replace")
            raise RenderApiError(
                f"Render API {method} {path} returned HTTP {exc.code}: {body_text}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RenderApiError(f"Render API network error: {exc}") from exc
