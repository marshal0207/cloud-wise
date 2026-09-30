"""
MongoDB Atlas Client.

Talks to the Atlas Administration API with the project's Atlas API key
pair:

    MONGODB_ATLAS_PUBLIC_KEY   → public key  (username of the pair)
    MONGODB_ATLAS_PRIVATE_KEY  → private key (password of the pair)
    MONGODB_ATLAS_PROJECT_ID   → project the pair may administer

Authentication
--------------
The Administration API authenticates API key pairs with **HTTP Digest
Authentication** (``WWW-Authenticate: Digest`` challenge/response). A
plain ``Authorization: Basic …`` header, and the OAuth
``client_credentials`` token endpoint, are both rejected with 401 for
this key type — verified against a live Atlas project. ``requests``'s
``HTTPDigestAuth`` performs the challenge/response, so the private key
only ever exists inside the auth object handed to the transport.

Security rules honoured here
----------------------------
* The private key is never logged, never returned and never written
  into a deployment payload, an application ``.env`` or a Docker
  Compose file.
* Error messages contain HTTP status codes and Atlas error messages
  only — never credentials, never the digest ``response`` digest.
"""

import logging
import time

import requests
from requests.auth import HTTPDigestAuth

logger = logging.getLogger(__name__)


class AtlasAuthError(Exception):
    """Credentials rejected, or the credentials lack the required role."""

    def __init__(self, message: str, http_status: int = 401):
        super().__init__(message)
        self.http_status = http_status


class AtlasApiError(Exception):
    """Atlas answered, but the request itself failed (404 / 429 / 5xx)."""

    def __init__(self, message: str, http_status: int = 0):
        super().__init__(message)
        self.http_status = http_status


class AtlasClient:
    API_BASE_URL = "https://cloud.mongodb.com/api/atlas/v2"

    def __init__(self, client_id: str, client_secret: str, project_id: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.project_id = project_id
        # Digest credentials: the object owns the key pair, the key pair
        # never leaves this object or the transport's Authorization header.
        self._auth = HTTPDigestAuth(client_id, client_secret)

    @staticmethod
    def _base_headers() -> dict:
        return {
            "Accept": "application/vnd.atlas.2023-01-01+json",
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, **kwargs):
        url = f"{self.API_BASE_URL}{path}"
        method = method.upper()

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.request(
                    method,
                    url,
                    headers=self._base_headers(),
                    auth=self._auth,
                    timeout=10,
                    **kwargs,
                )
            except requests.RequestException as exc:
                # Transport failure — never include request internals.
                logger.error(
                    "Atlas API transport error %s %s", method, path
                )
                raise AtlasApiError(
                    "Failed to communicate with the Atlas API"
                ) from exc

            if response.status_code == 429:
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise AtlasApiError("Rate limit exceeded", http_status=429)

            if response.status_code in (401, 403):
                logger.error(
                    "Atlas API rejected %s %s (HTTP %s)",
                    method, path, response.status_code,
                )
                if response.status_code == 401:
                    raise AtlasAuthError(
                        "MongoDB Atlas rejected the configured API key "
                        f"(HTTP 401). Check MONGODB_ATLAS_PUBLIC_KEY / "
                        "MONGODB_ATLAS_PRIVATE_KEY and the key's Project "
                        "Network Access Manager role.",
                        http_status=401,
                    )
                raise AtlasAuthError(
                    "MongoDB Atlas credentials are not allowed to perform "
                    f"this action (HTTP 403). Grant the key the Project "
                    "Network Access Manager role for project "
                    f"{self.project_id}.",
                    http_status=403,
                )

            if response.status_code == 404:
                raise AtlasApiError(
                    "Atlas resource not found (invalid project ID or path)",
                    http_status=404,
                )

            if not response.ok:
                logger.error(
                    "Atlas API error %s %s (HTTP %s)",
                    method, path, response.status_code,
                )
                raise AtlasApiError(
                    f"Atlas API request failed (HTTP {response.status_code})",
                    http_status=response.status_code,
                )

            try:
                return response.json() if response.content else None
            except ValueError as exc:
                raise AtlasApiError("Atlas returned an unreadable response") from exc

        raise AtlasApiError("Max retries exceeded")

    def get_project(self) -> dict:
        """Fetch the configured Atlas project (verifies project access)."""
        data = self._request("GET", f"/groups/{self.project_id}")
        return dict(data or {})

    def get_network_access_list(self) -> list:
        """Get the current IP access list for the project."""
        path = f"/groups/{self.project_id}/accessList"
        data = self._request("GET", path)
        return (data or {}).get("results", [])

    def add_network_access_entry(self, ip_address: str, comment: str = ""):
        """Add an IP address to the project's access list."""
        path = f"/groups/{self.project_id}/accessList"
        payload = [
            {
                "ipAddress": ip_address,
                "comment": comment,
            }
        ]
        return self._request("POST", path, json=payload)
