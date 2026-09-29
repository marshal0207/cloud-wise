"""
MongoDB Atlas Network Access automation (optional, additive).

Why this exists
---------------
CloudWise never provisions a database — the deployed repository points at an
external one. The instance gets its public IPv4 address at launch, and a
MongoDB Atlas cluster with IP allowlisting refuses every address that is not
on its access list. The application then dies with a driver server-selection
error while the HTTP probe only reports a bare ``502``.

This module adds the missing piece: once the instance has a public IP,
CloudWise can (when the operator configured Atlas API credentials) add a
**narrow /32 entry** for that address to the project's Atlas access list.

Safety rules honoured here
--------------------------
* **No application credentials are read, stored or logged** — only the
  Atlas *administration* credentials the operator configured themselves.
* The Atlas private key never leaves this module: it is only used to build
  an ``Authorization`` header that is never printed.
* Only ``/32`` entries are written. ``0.0.0.0/0`` is never produced.
* Entries are tagged ``CloudWise deployment <deployment-id>`` so a later
  cleanup can tell CloudWise-managed entries from hand-made ones.
* When the operator did **not** configure Atlas credentials this module
  reports ``configured: False`` — it never pretends allowlisting happened.
* When the connection string is not an Atlas one, nothing is attempted.

Standard library only (``urllib``): the project does not ship ``requests``.
"""

from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Mapping

ATLAS_API_BASE = "https://cloud.mongodb.com/api/atlas/v2"
HTTP_TIMEOUT_SECONDS = 15

ENTRY_COMMENT_PREFIX = "CloudWise deployment "

# Deployment error code used when Atlas automation was configured but the
# Admin API rejected the request.
ERROR_ATLAS_ACCESS_FAILED = "MONGODB_ATLAS_ACCESS_FAILED"

# Conventional environment variable names a repository may use for its
# MongoDB connection string (value with a mongodb:// scheme wins first).
MONGODB_ENV_VAR_NAMES: tuple[str, ...] = (
    "MONGO_URI",
    "MONGODB_URI",
    "MONGO_URL",
    "MONGO_CONNECTION_URI",
    "MONGO_DB_URI",
    "MONGODB_URL",
    "DATABASE_URL",
)

_HOST_SUFFIXES = (".mongodb.net", ".mongodb.com", ".mongodb-test.net")
_IPV4_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")
# process.env.X / os.getenv("X") / os.environ['X'] / ${X} / ENV["X"]
_ENV_REFERENCE_RE = re.compile(
    r"""(?:process\.env\.|os\.getenv\(\s*['"]|os\.environ\[\s*['"]|\$\{|ENV\[\s*['"])"""
    r"""([A-Z][A-Z0-9_]{2,})"""
)


# ---------------------------------------------------------------------------
# configuration
# ---------------------------------------------------------------------------

def atlas_credentials() -> tuple[str, str, str]:
    """``(public_key, private_key, project_id)`` — never logged anywhere."""
    try:
        from django.conf import settings

        public_key = str(getattr(settings, "MONGODB_ATLAS_PUBLIC_KEY", "") or "")
        private_key = str(getattr(settings, "MONGODB_ATLAS_PRIVATE_KEY", "") or "")
        project_id = str(getattr(settings, "MONGODB_ATLAS_PROJECT_ID", "") or "")
    except Exception:  # noqa: BLE001 — settings unavailable (pure unit tests)
        return "", "", ""
    return public_key.strip(), private_key.strip(), project_id.strip()


def atlas_configured() -> bool:
    """True only when *all* three Atlas API values are present."""
    public_key, private_key, project_id = atlas_credentials()
    return bool(public_key and private_key and project_id)


def atlas_status() -> dict[str, Any]:
    """Safe (secret-free) description of the Atlas automation configuration."""
    public_key, _, project_id = atlas_credentials()
    configured = bool(public_key and project_id) and bool(atlas_credentials()[1])
    return {
        "configured": configured,
        "publicKeyPresent": bool(public_key),
        "privateKeyPresent": bool(atlas_credentials()[1]),
        "projectIdPresent": bool(project_id),
        # Identifier only — never a credential.
        "publicKeyId": f"{public_key[:4]}…" if public_key else "",
    }


# ---------------------------------------------------------------------------
# connection-string inspection (credentials are dropped immediately)
# ---------------------------------------------------------------------------

def is_atlas_host(host: object) -> bool:
    """True for a MongoDB Atlas style host name."""
    text = str(host or "").strip().lower().rstrip(".")
    if not text:
        return False
    return any(text.endswith(suffix) for suffix in _HOST_SUFFIXES)


def is_ipv4(value: object) -> bool:
    text = str(value or "").strip()
    if not _IPV4_RE.match(text):
        return False
    try:
        return all(0 <= int(part) <= 255 for part in text.split("."))
    except ValueError:
        return False


def inspect_connection_uri(value: object) -> dict[str, Any]:
    """
    Describe a MongoDB connection string **without ever keeping secrets**.

    Returns ``{"detected": bool, "scheme", "host", "port", "srv", "atlas",
    "hasDatabaseName"}``. Userinfo (``user:password@``) is discarded inside
    this function, so no credential can leak into logs, plans or errors.
    """
    empty: dict[str, Any] = {
        "detected": False,
        "scheme": "",
        "host": "",
        "port": 0,
        "srv": False,
        "atlas": False,
        "hasDatabaseName": False,
    }
    raw = str(value or "").strip()
    if not raw or "://" not in raw:
        return empty
    try:
        parts = urllib.parse.urlsplit(raw)
    except ValueError:
        return empty
    scheme = (parts.scheme or "").lower()
    if scheme not in ("mongodb", "mongodb+srv"):
        return empty

    netloc = parts.netloc.rsplit("@", 1)[-1]  # drop user:password@
    seed = netloc.split(",")[0].strip()
    host, _, port_text = seed.partition(":")
    host = host.strip().lower().rstrip(".")
    if not host:
        return empty
    try:
        port = int(port_text)
    except ValueError:
        port = 0
    srv = scheme == "mongodb+srv"
    return {
        "detected": True,
        "scheme": scheme,
        "host": host,
        "port": port or (27017 if not srv else 0),
        "srv": srv,
        "atlas": is_atlas_host(host),
        "hasDatabaseName": bool(parts.path.strip("/")),
    }


def find_database_env_var(
    env_vars: Mapping[str, Any] | None = None,
    *,
    files: Mapping[str, str] | None = None,
) -> str:
    """
    Best-effort name of the repository's MongoDB environment variable.

    Order: a value that *is* a ``mongodb://`` / ``mongodb+srv://`` string,
    then a conventional name that is configured, then a name referenced by
    the repository source / ``.env.example``. Returns ``""`` when unknown —
    never a guess that would be written into a compose file.
    """
    values = {
        str(key): str(value)
        for key, value in dict(env_vars or {}).items()
        if str(key).strip()
    }
    for name in MONGODB_ENV_VAR_NAMES:
        if inspect_connection_uri(values.get(name)).get("detected"):
            return name
    for name in MONGODB_ENV_VAR_NAMES:
        if name in values:
            return name

    for key, content in dict(files or {}).items():
        lowered = str(key).replace("\\", "/").lower()
        if not lowered.endswith((".js", ".mjs", ".cjs", ".ts", ".py", ".env.example",
                                 ".env.sample", ".txt", ".md")):
            continue
        for match in _ENV_REFERENCE_RE.finditer(str(content or "")):
            if match.group(1) in MONGODB_ENV_VAR_NAMES:
                return match.group(1)
        for name in MONGODB_ENV_VAR_NAMES:
            if re.search(rf"^\s*{re.escape(name)}\s*=", str(content or ""),
                         re.MULTILINE):
                return name
    return ""


def describe_uri_for_deployment(
    env_vars: Mapping[str, Any] | None = None,
    *,
    files: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """
    Combine the variable *name* and the URI *shape* for a deployment.

    Only the safe fields listed in the docstring of
    :func:`inspect_connection_uri` are returned — never the value itself.
    """
    var_name = find_database_env_var(env_vars, files=files)
    inspected = inspect_connection_uri(
        (dict(env_vars or {}) or {}).get(var_name)
    )
    return {
        "envVar": var_name,
        "scheme": inspected["scheme"],
        "host": inspected["host"],
        "srv": inspected["srv"],
        "atlas": inspected["atlas"],
        "hasDatabaseName": inspected["hasDatabaseName"],
        "uriAvailable": bool(inspected["detected"]),
    }


# ---------------------------------------------------------------------------
# Atlas Admin API (HTTP Basic: public key / private key)
# ---------------------------------------------------------------------------

def _request(
    method: str,
    path: str,
    *,
    body: Any = None,
    timeout: float = HTTP_TIMEOUT_SECONDS,
) -> tuple[int, dict[str, Any]]:
    """
    Call the Atlas Admin API. Returns ``(status_code, payload)``.

    ``status == 0`` means the request never reached the API (network /
    TLS / DNS problem). The Authorization header is built here and never
    returned, stored or logged.
    """
    public_key, private_key, _ = atlas_credentials()
    if not (public_key and private_key):
        return 0, {"detail": "Atlas API credentials are not configured."}

    url = f"{ATLAS_API_BASE}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=data, method=method.upper())
    request.add_header("Accept", "application/json")
    request.add_header(
        "Authorization",
        "Basic "
        + base64.b64encode(f"{public_key}:{private_key}".encode("utf-8")).decode(
            "ascii"
        ),
    )
    if data is not None:
        request.add_header("Content-Type", "application/json")

    def _payload(raw: bytes) -> dict[str, Any]:
        try:
            parsed = json.loads(raw.decode("utf-8", "replace"))
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.getcode() or 200), _payload(response.read(65536))
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read(65536)
        except Exception:  # noqa: BLE001
            raw = b""
        return int(exc.code or 0), _payload(raw)
    except Exception:  # noqa: BLE001 — never surface request internals
        return 0, {"detail": "The MongoDB Atlas API could not be reached."}


def _detail(payload: Mapping[str, Any] | None) -> str:
    data = dict(payload or {})
    for key in ("detail", "error", "reason", "message"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:300]
    return ""


def _project_path() -> str:
    _, _, project_id = atlas_credentials()
    return f"/groups/{urllib.parse.quote(project_id, safe='')}/accessList"


def entry_comment(deployment_id: object) -> str:
    """Clear, recognisable description for a CloudWise-managed entry."""
    text = str(deployment_id or "").strip() or "unknown"
    text = re.sub(r"\s+", " ", text)
    return f"{ENTRY_COMMENT_PREFIX}{text}"[:250]


def list_access_entries() -> tuple[list[dict[str, Any]], str]:
    """``(entries, error)`` — ``error`` is ``""`` on success."""
    if not atlas_configured():
        return [], "MongoDB Atlas API credentials are not configured."
    status, payload = _request("GET", _project_path())
    if status in (200, 204):
        results = payload.get("results")
        if not isinstance(results, list):
            return [], ""
        return [item for item in results if isinstance(item, dict)], ""
    if status == 0:
        return [], _detail(payload) or "The MongoDB Atlas API could not be reached."
    return [], _detail(payload) or f"Atlas access-list request failed (HTTP {status})."


def _entry_cidr(entry: Mapping[str, Any]) -> str:
    cidr = str(entry.get("cidrBlock") or "").strip()
    if cidr:
        return cidr
    ip = str(entry.get("ipAddress") or "").strip()
    return f"{ip}/32" if ip else ""


def ensure_atlas_access_entry(
    *,
    public_ip: str,
    deployment_id: object,
) -> dict[str, Any]:
    """
    Make sure ``<public_ip>/32`` is on the Atlas project access list.

    Returns a secret-free report::

        {"configured": bool, "action": added|exists|updated|skipped|failed,
         "cidr": ..., "reason": ..., "message": ...}

    Never raises: a deployment must not fail because the *administration*
    API is unavailable — the database preflight / health check decides
    whether the connection actually works, and reports the precise reason.
    """
    report: dict[str, Any] = {
        "configured": atlas_configured(),
        "action": "skipped",
        "cidr": "",
        "reason": "",
        "message": "",
    }
    ip = str(public_ip or "").strip()
    if not is_ipv4(ip):
        report["reason"] = "no_public_ip"
        report["message"] = (
            "Atlas allowlisting skipped: the instance has no public IPv4 "
            "address yet."
        )
        return report

    cidr = f"{ip}/32"
    report["cidr"] = cidr

    if not report["configured"]:
        report["reason"] = "not_configured"
        report["message"] = (
            "MongoDB Atlas API credentials are not configured, so CloudWise "
            f"did not allowlist {cidr}. Add MONGODB_ATLAS_PUBLIC_KEY, "
            "MONGODB_ATLAS_PRIVATE_KEY and MONGODB_ATLAS_PROJECT_ID to "
            "enable automatic allowlisting, or allow this address in "
            "MongoDB Atlas Network Access."
        )
        return report

    entries, error = list_access_entries()
    if error:
        report.update(action="failed", reason="api_error")
        report["message"] = (
            f"MongoDB Atlas access list could not be read ({error}). "
            f"Verify {cidr} is allowed in MongoDB Atlas Network Access."
        )
        return report

    comment = entry_comment(deployment_id)
    for entry in entries:
        if _entry_cidr(entry) != cidr:
            continue
        existing_comment = str(entry.get("comment") or "")
        if existing_comment == comment:
            report.update(action="exists")
            report["message"] = (
                f"Atlas Network Access already allows {cidr} "
                f"(\"{existing_comment}\")."
            )
            return report
        # Reuse the entry; refresh the description when it is CloudWise's
        # own (or blank) so the console shows the current deployment.
        if not existing_comment or existing_comment.startswith(
            ENTRY_COMMENT_PREFIX
        ):
            status, payload = _request(
                "PUT",
                f"{_project_path()}/{urllib.parse.quote(cidr, safe='')}",
                body={"comment": comment},
            )
            if status in (200, 204):
                report.update(action="updated")
                report["message"] = (
                    f"Atlas Network Access entry {cidr} updated to "
                    f"\"{comment}\"."
                )
                return report
        report.update(action="exists")
        report["message"] = (
            f"Atlas Network Access already allows {cidr} (existing entry "
            "kept unchanged)."
        )
        return report

    status, payload = _request(
        "POST",
        _project_path(),
        body=[{"cidrBlock": cidr, "comment": comment}],
    )
    if status in (200, 201, 204):
        report.update(action="added")
        report["message"] = (
            f"Added MongoDB Atlas Network Access entry {cidr} "
            f"(\"{comment}\")."
        )
        return report
    if status == 409:
        report.update(action="exists")
        report["message"] = (
            f"Atlas Network Access already contains {cidr}; entry reused."
        )
        return report

    report.update(action="failed", reason=f"http_{status}" if status else "api_error")
    report["message"] = (
        "MongoDB Atlas Network Access could not be updated for "
        f"{cidr} ({_detail(payload) or 'request rejected'}). Add {cidr} "
        "manually in Atlas Network Access (never 0.0.0.0/0)."
    )
    return report


def remove_atlas_access_entry(
    *,
    public_ip: str,
    deployment_id: object,
) -> dict[str, Any]:
    """
    Delete the CloudWise-managed ``/32`` entry for this address.

    **Only entries whose description starts with** ``CloudWise deployment``
    are removed, so a hand-made allowlist entry is never destroyed. Used
    when the instance is gone (termination) — a retained instance keeps its
    entry because the next deployment still needs it.
    """
    report: dict[str, Any] = {
        "configured": atlas_configured(),
        "action": "skipped",
        "cidr": "",
        "message": "",
    }
    ip = str(public_ip or "").strip()
    if not is_ipv4(ip) or not report["configured"]:
        report["message"] = (
            "Atlas Network Access cleanup skipped (no address or Atlas API "
            "credentials not configured)."
        )
        return report

    cidr = f"{ip}/32"
    report["cidr"] = cidr
    entries, error = list_access_entries()
    if error:
        report.update(action="failed")
        report["message"] = f"Atlas access list could not be read ({error})."
        return report

    for entry in entries:
        if _entry_cidr(entry) != cidr:
            continue
        comment = str(entry.get("comment") or "")
        if not comment.startswith(ENTRY_COMMENT_PREFIX):
            report.update(action="kept")
            report["message"] = (
                f"Kept {cidr}: the entry was not created by CloudWise."
            )
            return report
        status, payload = _request(
            "DELETE",
            f"{_project_path()}/{urllib.parse.quote(cidr, safe='')}",
        )
        if status in (200, 204, 404):
            report.update(action="removed")
            report["message"] = (
                f"Removed CloudWise Atlas Network Access entry {cidr}."
            )
            return report
        report.update(action="failed")
        report["message"] = (
            f"Atlas Network Access entry {cidr} could not be removed "
            f"({_detail(payload) or f'HTTP {status}'})."
        )
        return report

    report.update(action="absent")
    report["message"] = f"No CloudWise Atlas Network Access entry for {cidr}."
    return report
