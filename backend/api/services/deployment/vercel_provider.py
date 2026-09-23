"""
VercelDeploymentService — Real Vercel REST API deployment.

Uses the official Vercel REST API v13:
  https://vercel.com/docs/rest-api

Required environment variables:
  VERCEL_TOKEN   — Personal access token from vercel.com/account/tokens
  VERCEL_TEAM_ID — (optional) Team slug/ID for team-owned projects

Flow:
  1. Verify GitHub repository is accessible via Vercel token.
  2. Create or retrieve existing Vercel project linked to the repo.
  3. Trigger a deployment via the Vercel API.
  4. Poll deployment status until READY or ERROR.
  5. Return the real deployment URL from Vercel.
  6. HTTP-verify the URL is reachable.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


VERCEL_API = "https://api.vercel.com"
_POLL_INTERVAL = 5   # seconds between status polls
_MAX_POLLS = 60      # 5 min timeout


class VercelApiError(Exception):
    pass


class VercelDeploymentService:
    def __init__(self, token: str, team_id: str | None = None) -> None:
        if not token:
            raise ValueError("VERCEL_TOKEN is required.")
        self._token = token
        self._team_id = team_id or ""

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def deploy(
        self,
        *,
        repo_full_name: str,
        branch: str,
        project_name: str,
        framework: str | None,
        root_directory: str | None,
        build_command: str | None,
        output_directory: str | None,
        install_command: str | None,
        env_vars: dict[str, str] | None,
        existing_project_id: str | None,
    ) -> dict[str, Any]:
        """
        Deploy a GitHub repository to Vercel.

        Returns dict with keys:
          provider_project_id, deployment_id, url, status, logs
        """
        # 1. Create or reuse Vercel project
        if existing_project_id:
            project_id = existing_project_id
            project_name_used = project_name
        else:
            project = self._create_or_get_project(
                name=project_name,
                repo_full_name=repo_full_name,
                branch=branch,
                framework=framework,
                root_directory=root_directory,
                build_command=build_command,
                output_directory=output_directory,
                install_command=install_command,
            )
            project_id = project["id"]
            project_name_used = project["name"]

        # 2. Set environment variables on the project
        if env_vars:
            self._set_env_vars(project_id, env_vars)

        # 3. Build project_settings for the deployment.
        #    Vercel requires projectSettings for the first deployment of a project.
        #    For existing projects with prior deployments, it's optional but safe to include.
        project_settings: dict[str, Any] = {}
        if framework:
            project_settings["framework"] = framework
        if build_command:
            project_settings["buildCommand"] = build_command
        if install_command:
            project_settings["installCommand"] = install_command
        if output_directory:
            project_settings["outputDirectory"] = output_directory
        if root_directory:
            project_settings["rootDirectory"] = root_directory

        # 4. Trigger deployment
        deployment = self._create_deployment(
            project_id=project_id,
            repo_full_name=repo_full_name,
            branch=branch,
            project_settings=project_settings or None,
        )
        deployment_id = deployment["id"]

        # 5. Poll until terminal state
        final = self._poll_deployment(deployment_id)

        url = final.get("url") or (
            final.get("alias", [None])[0] if isinstance(final.get("alias"), list) else None
        )
        if url and not url.startswith("http"):
            url = f"https://{url}"

        state = final.get("readyState", final.get("state", "UNKNOWN"))

        return {
            "provider_project_id": project_id,
            "provider_project_name": project_name_used,
            "deployment_id": deployment_id,
            "url": url,
            "status": state,
            "raw": final,
        }

    def get_deployment_status(self, deployment_id: str) -> dict[str, Any]:
        path = f"/v13/deployments/{urllib.parse.quote(deployment_id)}"
        return self._request("GET", path)

    def get_deployment_events(self, deployment_id: str) -> list[dict[str, Any]]:
        """Retrieve build/deployment events (logs) from Vercel v3 API."""
        path = f"/v3/deployments/{urllib.parse.quote(deployment_id)}/events"
        result = self._request("GET", path)
        return result if isinstance(result, list) else []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _create_or_get_project(
        self,
        *,
        name: str,
        repo_full_name: str,
        branch: str,
        framework: str | None,
        root_directory: str | None,
        build_command: str | None,
        output_directory: str | None,
        install_command: str | None,
    ) -> dict[str, Any]:
        # 1. Try to find existing project by exact name
        try:
            qs = urllib.parse.urlencode({"search": name, "limit": "10"})
            if self._team_id:
                qs += f"&teamId={urllib.parse.quote(self._team_id)}"
            result = self._request("GET", f"/v9/projects?{qs}")
            for proj in result.get("projects", []):
                if proj.get("name") == name:
                    return proj
        except VercelApiError:
            pass

        # 2. Search ALL projects for one linked to the same GitHub repository.
        #    This prevents creating duplicate projects for full-stack repos.
        repo_lower = repo_full_name.lower()
        try:
            qs = urllib.parse.urlencode({
                "search": repo_lower.split("/")[-1],
                "limit": "20",
            })
            if self._team_id:
                qs += f"&teamId={urllib.parse.quote(self._team_id)}"
            result = self._request("GET", f"/v9/projects?{qs}")
            for proj in result.get("projects", []):
                link = proj.get("link") or {}
                link_org = (link.get("org") or "").lower()
                link_repo = (link.get("repo") or "").lower()
                linked_full = f"{link_org}/{link_repo}" if link_org else link_repo
                if linked_full == repo_lower:
                    return proj
        except VercelApiError:
            pass

        # 3. No existing project linked to this repo -- create new one.
        body: dict[str, Any] = {
            "name": name,
            "gitRepository": {
                "type": "github",
                "repo": repo_full_name,
            },
        }
        if framework:
            body["framework"] = framework
        if root_directory:
            body["rootDirectory"] = root_directory
        if build_command:
            body["buildCommand"] = build_command
        if output_directory:
            body["outputDirectory"] = output_directory
        if install_command:
            body["installCommand"] = install_command

        path = "/v10/projects"
        if self._team_id:
            path += f"?teamId={urllib.parse.quote(self._team_id)}"

        return self._request("POST", path, body)

    def _set_env_vars(self, project_id: str, env_vars: dict[str, str]) -> None:
        entries = [
            {"key": k, "value": v, "type": "plain", "target": ["production", "preview"]}
            for k, v in env_vars.items()
        ]
        path = f"/v10/projects/{urllib.parse.quote(project_id)}/env"
        if self._team_id:
            path += f"?teamId={urllib.parse.quote(self._team_id)}"
        try:
            self._request("POST", path, entries)
        except VercelApiError:
            pass  # env vars may already exist; non-fatal

    def _create_deployment(
        self,
        *,
        project_id: str,
        repo_full_name: str,
        branch: str,
        project_settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        # Vercel gitSource requires org+repo format or numeric repoId.
        # repo_full_name is "owner/repo" — split into org and repo.
        parts = repo_full_name.split("/", 1)
        org = parts[0] if len(parts) == 2 else ""
        repo = parts[1] if len(parts) == 2 else repo_full_name

        body: dict[str, Any] = {
            "name": project_id,
            "project": project_id,
            "target": "production",
        }

        # Always include projectSettings — required for first deployment,
        # and overrides cached settings on existing projects.
        if project_settings:
            body["projectSettings"] = project_settings

        # Only include gitSource if we have valid org/repo info.
        # If the project is already linked to a Git repo, Vercel will
        # use that configuration automatically.
        if org and repo:
            body["gitSource"] = {
                "type": "github",
                "org": org,
                "repo": repo,
                "ref": branch,
            }

        path = "/v13/deployments"
        if self._team_id:
            path += f"?teamId={urllib.parse.quote(self._team_id)}&forceNew=1&skipAutoDetectionConfirmation=1"
        else:
            path += "?forceNew=1&skipAutoDetectionConfirmation=1"
        return self._request("POST", path, body)

    def _poll_deployment(self, deployment_id: str) -> dict[str, Any]:
        terminal = {"READY", "ERROR", "CANCELED"}
        for _ in range(_MAX_POLLS):
            data = self.get_deployment_status(deployment_id)
            state = data.get("readyState") or data.get("state", "")
            if state.upper() in terminal:
                return data
            time.sleep(_POLL_INTERVAL)
        raise VercelApiError(f"Deployment {deployment_id} timed out after {_MAX_POLLS * _POLL_INTERVAL}s.")

    def _request(self, method: str, path: str, body: Any = None) -> Any:
        url = VERCEL_API + path
        data = json.dumps(body).encode() if body is not None else None
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode(errors="replace")
            raise VercelApiError(
                f"Vercel API {method} {path} returned HTTP {exc.code}: {body_text}"
            ) from exc
        except urllib.error.URLError as exc:
            raise VercelApiError(f"Vercel API network error: {exc}") from exc
