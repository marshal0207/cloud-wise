"""
Verify CloudWise's MongoDB Atlas authorization before a connection is
recorded as ``connected``.

``connected`` means **all** of the following are true:

1. Atlas authentication succeeded — the configured API key pair
   (``MONGODB_ATLAS_PUBLIC_KEY`` / ``MONGODB_ATLAS_PRIVATE_KEY``)
   passed the Administration API's HTTP Digest challenge.
2. The configured project (``MONGODB_ATLAS_PROJECT_ID``) is readable,
   so CloudWise knows which project it would allowlist IPs in.
3. The project's Network Access list can be read — the key carries the
   role CloudWise needs to add ``<ec2-ip>/32`` entries during a
   deployment.

If Atlas answers 401 or 403 at any step the caller must **not** create
or keep a ``connected`` record. Credentials are never logged and never
part of the returned mapping.
"""

from __future__ import annotations

from .atlas_client import AtlasApiError, AtlasAuthError, AtlasClient

# Error codes surfaced to the Connect Atlas endpoint.
CODE_AUTH_FAILED = "ATLAS_AUTH_FAILED"
CODE_PROJECT_ACCESS_DENIED = "ATLAS_PROJECT_ACCESS_DENIED"
CODE_PROJECT_NOT_FOUND = "ATLAS_PROJECT_NOT_FOUND"
CODE_NETWORK_ACCESS_DENIED = "ATLAS_NETWORK_ACCESS_PERMISSION_DENIED"
CODE_API_FAILED = "ATLAS_API_FAILED"


def _failure(http_status: int, error_code: str, message: str) -> dict:
    return {
        "ok": False,
        "http_status": http_status,
        "error_code": error_code,
        "message": message,
        "project_id": "",
        "project_name": "",
    }


def verify_atlas_authorization(client: AtlasClient) -> dict:
    """
    Authenticate against MongoDB Atlas and verify the configured
    project plus Network Access management permission.

    Never raises: every failure is returned as ``{"ok": False, ...}``
    with an HTTP status the API can map directly (401/403 → do not
    connect, 502 → Atlas/transport problem).
    """
    if not (client.client_id and client.client_secret and client.project_id):
        return _failure(
            400,
            "ATLAS_NOT_CONFIGURED",
            "MongoDB Atlas credentials are not configured. Set "
            "MONGODB_ATLAS_PUBLIC_KEY, MONGODB_ATLAS_PRIVATE_KEY and "
            "MONGODB_ATLAS_PROJECT_ID in the backend .env file.",
        )

    # 1 + 2 — authenticate (HTTP Digest challenge) *and* read the
    # configured project. Digest authentication only succeeds when the
    # key pair is accepted, so a 401 here means "not connected".
    try:
        project = client.get_project()
    except AtlasAuthError as exc:
        if getattr(exc, "http_status", 401) == 403:
            return _failure(
                403,
                CODE_PROJECT_ACCESS_DENIED,
                f"Atlas credentials cannot access project "
                f"{client.project_id}: {exc}",
            )
        return _failure(401, CODE_AUTH_FAILED, str(exc))
    except AtlasApiError as exc:
        if getattr(exc, "http_status", 0) == 404:
            return _failure(
                404,
                CODE_PROJECT_NOT_FOUND,
                f"Atlas project {client.project_id} was not found: {exc}",
            )
        return _failure(
            502,
            CODE_API_FAILED,
            f"Atlas project {client.project_id} could not be read: {exc}",
        )

    # 3 — Network Access list must be readable (allowlisting permission)
    try:
        client.get_network_access_list()
    except AtlasAuthError as exc:
        if getattr(exc, "http_status", 403) == 401:
            return _failure(401, CODE_AUTH_FAILED, str(exc))
        return _failure(
            403,
            CODE_NETWORK_ACCESS_DENIED,
            "The Atlas API key can authenticate but is not allowed to "
            "manage this project's Network Access list. Grant it the "
            "Project Network Access Manager role and try again. "
            f"({exc})",
        )
    except AtlasApiError as exc:
        return _failure(
            502,
            CODE_API_FAILED,
            f"Atlas Network Access list could not be read: {exc}",
        )

    return {
        "ok": True,
        "http_status": 200,
        "error_code": "",
        "message": (
            f"Verified Atlas access to project {client.project_id} "
            "(authentication, project access and Network Access "
            "management)."
        ),
        "project_id": client.project_id,
        "project_name": str((project or {}).get("name") or ""),
    }
