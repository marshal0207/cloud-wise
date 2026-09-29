"""
Database preflight: detect the external database, verify it from the
instance, and turn a failed health check into an actionable error code.

Why this exists
---------------
CloudWise never provisions a database — the repository points at an
external one (MongoDB Atlas, Neon, RDS, PlanetScale, ...). The instance
receives a **new public IP on every rebuild**, so the database's network
access list usually still holds the previous address and the application
dies with a driver timeout while the HTTP health check only reports a bare
"502".

The preflight runs on the instance before the deployment is declared
healthy and answers, with markers only (never a connection string):

    CLOUDWISE_DB_PROBE kind=mongodb env=ok dns=ok tcp=fail verdict=unreachable
    CLOUDWISE_PROXY api=502 proxy=nginx

Failure verdicts map to stable error codes so the UI can tell a database
problem apart from a dead backend, a broken nginx route or a dead frontend:

    env=missing   → DATABASE_ENV_MISSING
    dns/tcp=fail  → DATABASE_CONNECTION_FAILED
    (health only) → BACKEND_NOT_RUNNING / NGINX_PROXY_FAILED / FRONTEND_FAILED

Everything here is detection/reporting: no existing deployment command,
port, nginx route or state transition is changed, and no probe result can
alter a deployment that already passed its health checks.
"""

from __future__ import annotations

import base64
import re
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit

from . import database_probe
from .mongodb_atlas_service import atlas_configured, is_atlas_host

# ---------------------------------------------------------------------------
# database kinds
# ---------------------------------------------------------------------------

KIND_MONGODB = "mongodb"
KIND_POSTGRESQL = "postgresql"
KIND_MYSQL = "mysql"

DEFAULT_PORTS: dict[str, int] = {
    KIND_MONGODB: 27017,
    KIND_POSTGRESQL: 5432,
    KIND_MYSQL: 3306,
}

SCHEME_KIND: dict[str, str] = {
    "mongodb": KIND_MONGODB,
    "mongodb+srv": KIND_MONGODB,
    "postgres": KIND_POSTGRESQL,
    "postgresql": KIND_POSTGRESQL,
    "mysql": KIND_MYSQL,
}

_TYPE_KIND = {
    "mongodb": KIND_MONGODB,
    "postgresql": KIND_POSTGRESQL,
    "postgres": KIND_POSTGRESQL,
    "mysql": KIND_MYSQL,
}

# Conventional variable names per kind (a value with a matching URL scheme
# always wins — this is only the fallback when a value cannot be parsed).
ENV_VARS_BY_KIND: dict[str, tuple[str, ...]] = {
    KIND_MONGODB: (
        "MONGO_URI",
        "MONGODB_URI",
        "MONGO_URL",
        "MONGO_CONNECTION_URI",
        "MONGO_DB_URI",
        "DATABASE_URL",
    ),
    KIND_POSTGRESQL: (
        "DATABASE_URL",
        "POSTGRES_URI",
        "POSTGRESQL_URI",
        "POSTGRES_URL",
        "PG_URI",
    ),
    KIND_MYSQL: (
        "DATABASE_URL",
        "MYSQL_URI",
        "MYSQL_URL",
        "MYSQL_ROOT_URL",
    ),
}

# Error codes this module can produce for a failed deployment.
ERROR_DATABASE_ENV_MISSING = "DATABASE_ENV_MISSING"
ERROR_DATABASE_CONNECTION_FAILED = "DATABASE_CONNECTION_FAILED"
ERROR_BACKEND_NOT_RUNNING = "BACKEND_NOT_RUNNING"
ERROR_NGINX_PROXY_FAILED = "NGINX_PROXY_FAILED"
ERROR_FRONTEND_FAILED = "FRONTEND_FAILED"

# Additive codes so the UI can tell every failure mode apart instead of
# reporting a bare "health check failed":
#   A EC2_UNAVAILABLE           — the instance is not running
#   B DOCKER_UNAVAILABLE        — Docker/Compose missing or daemon down
#   C CONTAINER_FAILED          — a container exited / is restarting
#   D BACKEND_NOT_RUNNING       — backend up in Docker, not answering
#   E DATABASE_AUTH_FAILED      — MongoDB rejected the credentials
#   F MONGODB_ATLAS_NETWORK_BLOCKED — MongoDB network access denied
#   G NGINX_PROXY_FAILED / FRONTEND_FAILED — routing / frontend
#   H HEALTH_ENDPOINT_FAILED    — endpoint answered, but not healthy
ERROR_EC2_UNAVAILABLE = "EC2_UNAVAILABLE"
ERROR_DOCKER_UNAVAILABLE = "DOCKER_UNAVAILABLE"
ERROR_CONTAINER_FAILED = "CONTAINER_FAILED"
ERROR_DATABASE_AUTH_FAILED = "DATABASE_AUTH_FAILED"
ERROR_MONGODB_ATLAS_NETWORK_BLOCKED = "MONGODB_ATLAS_NETWORK_BLOCKED"
ERROR_MONGODB_ATLAS_NOT_CONFIGURED = "MONGODB_ATLAS_NOT_CONFIGURED"
ERROR_HEALTH_ENDPOINT_FAILED = "HEALTH_ENDPOINT_FAILED"

STATUS_SUCCESS = "SUCCESS"
STATUS_FAILED = "FAILED"
STATUS_SKIPPED = "SKIPPED"

PROBE_PATH = "/tmp/cloudwise_db_probe.py"
PROBE_B64_PATH = "/tmp/cloudwise_db_probe.b64"

_HOST_RE = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,251})$")
_DB_MARKER_RE = re.compile(r"CLOUDWISE_DB_PROBE[ \t]+([^\r\n]+)")
_PROXY_MARKER_RE = re.compile(
    r"CLOUDWISE_PROXY[ \t]+api=(\d{1,3})[ \t]+proxy=([A-Za-z_]+)"
)

# --- failure-signature detection (container diagnostics / driver logs) ------
# Docker itself unavailable (B).
_DOCKER_UNAVAILABLE_RE = re.compile(
    r"docker:\s*(command\s+)?not found"
    r"|docker compose not installed"
    r"|Cannot connect to the Docker daemon"
    r"|Is the docker daemon running",
    re.IGNORECASE,
)
# A compose/ps line that shows a container down (C).
_CONTAINER_DOWN_RE = re.compile(
    r"\b(?:Exited\s*\(\d+\)|Restarting\s*\(|Created\b|Removal in progress)",
    re.IGNORECASE,
)
_SERVICE_NAME_RE = re.compile(r"\b(frontend|backend|nginx)\b", re.IGNORECASE)
_CONTAINER_STATE_RE = re.compile(
    r"(Exited\s*\([^)]*\)|Restarting\s*\([^)]*\)[^,\n]*|Created)", re.IGNORECASE
)
# Machine-readable container state printed by the instance diagnostics:
#   CLOUDWISE_CONTAINER service=backend status=exited restarts=3 exit=1
# `docker compose ps` only prints human text, which is unreliable to parse,
# and it hides the restart counter that distinguishes "stopped once" from
# "crash-looping on every start".
_CONTAINER_MARKER_RE = re.compile(
    r"CLOUDWISE_CONTAINER[ \t]+service=(?P<service>\S+)[ \t]+"
    r"status=(?P<status>\S+)[ \t]+restarts=(?P<restarts>\d+)[ \t]+"
    r"exit=(?P<exit>-?\d+)",
    re.IGNORECASE,
)
# Verdict of the backend service gate (one word, never a sentence).
_GATE_RESULT_RE = re.compile(r"CLOUDWISE_GATE_RESULT[ \t]+(?P<result>\S+)")
# Statuses that mean the container is not serving traffic right now.
_DOWN_CONTAINER_STATUSES = frozenset(
    {"exited", "dead", "created", "restarting", "removing"}
)
# How many restarts before a container counts as crash-looping rather than
# recovering from a single transient failure.
_CRASH_LOOP_RESTARTS = 2
# The instance itself never became usable (A).
_EC2_UNAVAILABLE_RE = re.compile(
    r"did not reach running state"
    r"|instance\s+\S+\s+is not running"
    r"|instance\s+\S+\s+not found in AWS account",
    re.IGNORECASE,
)
# MongoDB driver: the credentials were rejected (E).
_MONGO_AUTH_RE = re.compile(
    r"authentication failed"
    r"|bad auth"
    r"|MongoServerError.*auth"
    r"|code\s*=?\s*18\b"
    r"|incorrect (user|username|password)"
    r"|AuthenticationFailed"
    r"|authSource",
    re.IGNORECASE,
)
# MongoDB driver: the network / allowlist refused the connection (F).
_MONGO_NETWORK_RE = re.compile(
    r"ReplicaSetNoPrimary"
    r"|Could not connect to any servers"
    r"|ServerSelectionTimedOut"
    r"|ServerSelectionError"
    r"|TopologyDescription"
    r"|getaddrinfo\b"
    r"|ETIMEDOUT"
    r"|ECONNREFUSED"
    r"|no route to host"
    r"|connection timed out",
    re.IGNORECASE,
)
# What the injected /api/health endpoint returns when the DB is down.
_DB_UNAVAILABLE_BODY_RE = re.compile(
    r"\"database\"\s*:\s*\"unavailable\"|status\"\s*:\s*\"unhealthy\"",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# connection-string parsing (host/port only — credentials are never kept)
# ---------------------------------------------------------------------------

def parse_database_url(value: object) -> dict[str, Any] | None:
    """
    Parse a database URL into ``kind/host/port/srv``.

    Returns ``None`` when the value carries no supported database scheme.
    Userinfo (``user:password@``) is dropped immediately, so no secret ever
    leaves this function.
    """
    raw = str(value or "").strip()
    if not raw or "://" not in raw:
        return None
    try:
        parts = urlsplit(raw)
    except ValueError:
        return None
    scheme = (parts.scheme or "").lower()
    kind = SCHEME_KIND.get(scheme)
    if kind is None:
        return None

    netloc = parts.netloc.rsplit("@", 1)[-1]  # drop userinfo
    seed = netloc.split(",", 1)[0].strip()  # first node of the seed list
    if not seed or seed.startswith("["):
        return None  # IPv6 literals are not probed
    host, _, port_text = seed.partition(":")
    host = host.strip().lower().rstrip(".")
    if not _HOST_RE.match(host):
        return None
    try:
        port = int(port_text)
    except ValueError:
        port = 0
    if not (0 < port < 65536):
        port = DEFAULT_PORTS[kind]
    return {
        "kind": kind,
        "host": host,
        "port": port,
        "srv": scheme == "mongodb+srv",
        "scheme": scheme,
    }


# ---------------------------------------------------------------------------
# dependency detection
# ---------------------------------------------------------------------------

def _first_present(names: Sequence[str], available: Mapping[str, Any]) -> str:
    for name in names:
        if name in available:
            return name
    return ""


def _kind_from_type(type_name: object) -> str:
    return _TYPE_KIND.get(str(type_name or "").strip().lower(), "")


def _kind_from_plan(plan: Mapping[str, Any]) -> str:
    database = plan.get("database") or {}
    if not isinstance(database, Mapping):
        return ""
    return _kind_from_type(database.get("type"))


def _kind_from_files(files: Mapping[str, str] | None) -> str:
    if not files:
        return ""
    try:
        from ..tech_stack_detector import detect_database

        detected = detect_database(files)
    except Exception:  # noqa: BLE001 — detection must never break a deploy
        return ""
    if not isinstance(detected, Mapping) or not detected.get("detected"):
        return ""
    return _kind_from_type(detected.get("type"))


def _ordered_env_names(env_vars: Mapping[str, str]) -> list[str]:
    """Preferred database variable names first, then the remaining names."""
    ordered: list[str] = []
    for names in ENV_VARS_BY_KIND.values():
        for name in names:
            if name in env_vars and name not in ordered:
                ordered.append(name)
    for name in sorted(env_vars):
        if name not in ordered:
            ordered.append(name)
    return ordered


def detect_database_dependency(
    *,
    files: Mapping[str, str] | None = None,
    env_vars: Mapping[str, Any] | None = None,
    plan: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """
    Work out which external database (if any) this deployment needs.

    Order of evidence — the most specific wins:

    1. an environment value that *is* a database URL (host + port + SRV)
    2. the deployment plan / repository analysis (MongoDB/PostgreSQL/MySQL)
       paired with a conventional variable name, when one is declared

    Returns ``None`` for repositories without an external database, which
    keeps the preflight inert for every non-database deployment.
    """
    values = {
        str(key): str(value)
        for key, value in dict(env_vars or {}).items()
        if str(key).strip()
    }
    plan = dict(plan or {})
    declared = {str(name): "1" for name in (plan.get("requiredEnvVars") or [])}

    for name in _ordered_env_names(values):
        parsed = parse_database_url(values.get(name))
        if parsed is None:
            continue
        return {
            "kind": parsed["kind"],
            "envVar": name,
            "host": parsed["host"],
            "port": int(parsed["port"]),
            "srv": bool(parsed["srv"]),
            "source": "uri",
        }

    kind = _kind_from_plan(plan) or _kind_from_files(files)
    if not kind:
        return None
    preferred = ENV_VARS_BY_KIND[kind]
    env_var = _first_present(preferred, values) or _first_present(
        preferred, declared
    )
    return {
        "kind": kind,
        "envVar": env_var,
        "host": "",
        "port": DEFAULT_PORTS[kind],
        "srv": False,
        "source": "analysis",
    }


# ---------------------------------------------------------------------------
# probe staging (the script is uploaded base64 through SSM)
# ---------------------------------------------------------------------------

def probe_source() -> str:
    """Source of the in-instance probe, or '' when it cannot be staged."""
    try:
        path = Path(str(database_probe.__file__ or ""))
        if path.suffix != ".py":
            return ""
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def build_probe_commands(
    dependency: Mapping[str, Any] | None,
    *,
    env_file: str,
    proxy_url: str = "",
) -> list[str]:
    """
    Shell commands that stage, run and remove the probe on the instance.

    The probe always exits 0 (a missing python runtime degrades to a
    ``status=unavailable`` marker) so this step can never fail a deployment
    that has nothing to report.
    """
    source = probe_source()
    if not source:
        return []
    encoded = base64.b64encode(source.encode("utf-8")).decode("ascii")
    dependency = dict(dependency or {})

    def _q(value: object) -> str:
        return str(value or "").replace("'", "").replace("\n", "").replace("\r", "")

    args = [
        "--kind",
        _q(dependency.get("kind")),
        "--env-file",
        _q(env_file),
        "--var",
        _q(dependency.get("envVar")),
        "--host",
        _q(dependency.get("host")),
        "--port",
        str(int(dependency.get("port") or 0)),
        "--srv",
        "1" if dependency.get("srv") else "0",
        "--proxy-url",
        _q(proxy_url),
    ]
    arg_text = " ".join(
        f"'{part}'" if index % 2 else part for index, part in enumerate(args)
    )

    commands = [f": > '{PROBE_B64_PATH}'"]
    for offset in range(0, len(encoded), 8000):
        commands.append(
            f"printf '%s' '{encoded[offset:offset + 8000]}' >> '{PROBE_B64_PATH}'"
        )
    commands.append(
        f"base64 -d '{PROBE_B64_PATH}' > '{PROBE_PATH}' 2>/dev/null || true"
    )
    commands.append(
        "{ command -v python3 >/dev/null 2>&1 && PY=python3 || PY=python; "
        f"$PY '{PROBE_PATH}' {arg_text} 2>/dev/null || "
        f"echo 'CLOUDWISE_DB_PROBE status=unavailable'; }} || "
        "echo 'CLOUDWISE_DB_PROBE status=unavailable'"
    )
    commands.append(f"rm -f '{PROBE_B64_PATH}' '{PROBE_PATH}' || true")
    return commands


def build_probe_url(app_port: int, probe_path: str = "") -> str:
    """URL the proxy probe hits on the instance (never a public address)."""
    try:
        port = int(app_port or 80)
    except (TypeError, ValueError):
        port = 80
    path = str(probe_path or "").strip()
    if not path.startswith("/") or re.search(r"[^A-Za-z0-9/._-]", path):
        path = "/"
    if port in (80, 443):
        return f"http://127.0.0.1{path}"
    return f"http://127.0.0.1:{port}{path}"


# ---------------------------------------------------------------------------
# marker parsing
# ---------------------------------------------------------------------------

def _fields(text: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for token in text.split():
        if "=" not in token:
            continue
        key, _, value = token.partition("=")
        parsed[key] = value
    return parsed


def parse_probe_output(output: str) -> dict[str, Any]:
    """
    Turn the instance output into a structured probe result.

    ``status`` is ``SKIPPED`` when nothing reported (mocked SSM, missing
    runtime) — a skipped probe must never fail a deployment.
    """
    text = str(output or "")
    result: dict[str, Any] = {
        "status": STATUS_SKIPPED,
        "kind": "none",
        "env": "unknown",
        "dns": "unknown",
        "tcp": "unknown",
        "verdict": database_probe.NOT_APPLICABLE,
        "proxy": {"statusCode": 0, "origin": "unknown"},
    }
    if not text.strip():
        return result

    db_match = _DB_MARKER_RE.search(text)
    if db_match is None:
        return result
    fields = _fields(db_match.group(1))
    if fields.get("status") == "unavailable":
        return result

    verdict = fields.get("verdict") or database_probe.VERDICT_UNKNOWN
    result.update(
        {
            "status": STATUS_SUCCESS,
            "kind": fields.get("kind") or "none",
            "env": fields.get("env") or "unknown",
            "dns": fields.get("dns") or "unknown",
            "tcp": fields.get("tcp") or "unknown",
            "verdict": verdict,
        }
    )
    proxy_match = _PROXY_MARKER_RE.search(text)
    if proxy_match is not None:
        try:
            code = int(proxy_match.group(1))
        except ValueError:
            code = 0
        result["proxy"] = {
            "statusCode": code,
            "origin": proxy_match.group(2),
        }
    return result


# ---------------------------------------------------------------------------
# report building
# ---------------------------------------------------------------------------

def _database_failure(
    probe: Mapping[str, Any],
    dependency: Mapping[str, Any],
    *,
    public_ip: str,
) -> tuple[str, str]:
    """(error_code, message) for a failed database preflight."""
    var_name = str(dependency.get("envVar") or "the database variable")
    kind = str(dependency.get("kind") or "database")
    host = str(dependency.get("host") or "")
    port = int(dependency.get("port") or 0)

    if probe.get("verdict") == database_probe.VERDICT_ENV_MISSING:
        return ERROR_DATABASE_ENV_MISSING, (
            f"Database preflight failed: environment variable {var_name} "
            "is missing or empty in the uploaded .env, so the application "
            "cannot open its database connection. Provide a value for "
            f"{var_name} (see .env.example) and deploy again."
        )

    checks = (
        f"variable {var_name} present, "
        f"DNS {'resolved' if probe.get('dns') == 'ok' else probe.get('dns')}, "
        f"TCP {'connected' if probe.get('tcp') == 'ok' else probe.get('tcp')}"
    )
    target = f" ({host}:{port})" if host and port else ""
    message = (
        f"Database preflight failed: this instance cannot reach its {kind} "
        f"database{target} — {checks}. "
        + (
            f"Deployment source IP: {public_ip}. "
            if public_ip
            else ""
        )
        + "Likely causes: the database network access list (for example "
        "MongoDB Atlas Network Access) still allows only a previous "
        f"instance IP, an inbound firewall/security-group rule blocks "
        f"port {port}, or the host name is wrong. "
        + (
            f"Allow {public_ip}/32 in the database network access list "
            "(never 0.0.0.0/0) and deploy again."
            if public_ip
            else "Allow this instance's public IP in the database network "
            "access list and deploy again."
        )
    )
    return ERROR_DATABASE_CONNECTION_FAILED, message


def build_preflight_report(
    *,
    dependency: Mapping[str, Any] | None = None,
    probe_output: str,
    public_ip: str = "",
) -> dict[str, Any]:
    """Assemble the report consumed by the provider, the logs and the UI."""
    dependency = dict(dependency or {})
    probe = parse_probe_output(probe_output)

    report: dict[str, Any] = {
        "status": probe["status"],
        "kind": probe.get("kind") or dependency.get("kind") or "none",
        "environmentVariable": str(dependency.get("envVar") or ""),
        "host": str(dependency.get("host") or ""),
        "port": int(dependency.get("port") or 0),
        "env": probe.get("env"),
        "dns": probe.get("dns"),
        "tcp": probe.get("tcp"),
        "verdict": probe.get("verdict"),
        "proxy": dict(probe.get("proxy") or {}),
        "errorCode": "",
        "message": "",
    }

    proxy = dict(report.get("proxy") or {})
    proxy_code = proxy.get("statusCode")
    proxy_origin = str(proxy.get("origin") or "")
    entry = ""
    if proxy_code:
        entry = f" HTTP entry point: {proxy_code}"
        if proxy_origin:
            entry += f" (origin {proxy_origin})"
        entry += "."

    if report["status"] != STATUS_SUCCESS:
        report["message"] = (
            "Database preflight skipped: the instance reported no probe "
            "result (no probe output available)."
        )
        return report

    if report["verdict"] == database_probe.VERDICT_NOT_APPLICABLE:
        report["message"] = (
            "No external database is declared by this repository; "
            "connectivity preflight not applicable." + entry
        )
        return report

    if report["verdict"] in (
        database_probe.VERDICT_ENV_MISSING,
        database_probe.VERDICT_UNREACHABLE,
    ):
        report["status"] = STATUS_FAILED
        error_code, message = _database_failure(
            report, dependency, public_ip=public_ip
        )
        report["errorCode"] = error_code
        report["message"] = message
    elif report["verdict"] == database_probe.VERDICT_REACHABLE:
        report["message"] = (
            f"Database {report['kind']} reachable from the instance "
            f"({report['dns']} DNS, {report['tcp']} TCP)." + entry
        )
    else:
        report["message"] = (
            "Database preflight inconclusive "
            f"(env={report['env']}, dns={report['dns']}, "
            f"tcp={report['tcp']}) — deployment continues."
        )
    return report


# ---------------------------------------------------------------------------
# health-failure classification
# ---------------------------------------------------------------------------

def _split_codes(split_report: Mapping[str, Any] | None) -> tuple[int | None, bool]:
    split = split_report or {}
    if not split:
        return None, True

    def _code(section: str) -> int | None:
        value = (split.get(section) or {}).get("statusCode")
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    frontend_ok = bool((split.get("frontend") or {}).get("ok"))
    return _code("backend"), frontend_ok


def _http_code(health_message: str) -> int | None:
    match = re.search(r"\bHTTP\s+(\d{3})\b", str(health_message or ""))
    if match is None:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _response_ok(status_code: object) -> bool:
    """A healthy application answer (2xx/3xx plus auth/method replies)."""
    try:
        code = int(status_code)
    except (TypeError, ValueError):
        return False
    return 200 <= code < 400 or code in (401, 403, 405)


def _mongo_signals(text: object) -> tuple[bool, bool]:
    """``(credentials_rejected, network_refused)`` seen in container logs."""
    body = str(text or "")
    if not body.strip():
        return False, False
    return bool(_MONGO_AUTH_RE.search(body)), bool(_MONGO_NETWORK_RE.search(body))


def _container_markers(diagnostics: object) -> list[dict[str, Any]]:
    """Parsed ``CLOUDWISE_CONTAINER`` state lines (newest first kept as-is)."""
    text = str(diagnostics or "")
    if not text.strip():
        return []
    markers: list[dict[str, Any]] = []
    for match in _CONTAINER_MARKER_RE.finditer(text):
        markers.append(
            {
                "service": str(match.group("service") or "").lower(),
                "status": str(match.group("status") or "").lower(),
                "restarts": int(match.group("restarts") or 0),
                "exit": int(match.group("exit") or 0),
            }
        )
    return markers


def _marker_is_down(marker: Mapping[str, Any]) -> bool:
    status = str(marker.get("status") or "")
    if status in _DOWN_CONTAINER_STATUSES:
        # A clean one-shot service (exited 0, never restarted) is normal in
        # some compose projects and must not be reported as a failure.
        if status == "exited" and int(marker.get("exit") or 0) == 0:
            return int(marker.get("restarts") or 0) > 0
        return True
    return False


def _marker_state(marker: Mapping[str, Any]) -> str:
    """Human-readable parenthetical state for a marker line."""
    status = str(marker.get("status") or "unknown")
    exit_code = int(marker.get("exit") or 0)
    restarts = int(marker.get("restarts") or 0)
    parts = [status]
    if status == "exited":
        parts.append(f"code {exit_code}")
    if restarts:
        parts.append(f"{restarts} restart(s)")
    return ", ".join(parts)


def _ordered_markers(
    diagnostics: object, *, down_only: bool = False
) -> list[dict[str, Any]]:
    """Markers with the backend first — the container a health check probes."""
    markers = _container_markers(diagnostics)
    if down_only:
        markers = [marker for marker in markers if _marker_is_down(marker)]
    order = {"backend": 0, "frontend": 1, "nginx": 2}
    return sorted(
        markers, key=lambda marker: order.get(str(marker.get("service")), 9)
    )


def gate_result(diagnostics: object) -> str:
    """The backend gate verdict (``listening``, ``crashloop``, ... ) or ''."""
    match = _GATE_RESULT_RE.search(str(diagnostics or ""))
    return str(match.group("result") or "").lower() if match else ""


def _stopped_container(diagnostics: object) -> tuple[str, str] | None:
    """``(service, state)`` for a container that is not running."""
    text = str(diagnostics or "")
    if not text.strip():
        return None
    marked = _ordered_markers(text, down_only=True)
    if marked:
        marker = marked[0]
        return str(marker.get("service") or "backend"), _marker_state(marker)
    for line in text.splitlines():
        if not _CONTAINER_DOWN_RE.search(line):
            continue
        service = _SERVICE_NAME_RE.search(line)
        if service is None:
            continue
        state = _CONTAINER_STATE_RE.search(line)
        return service.group(1).lower(), (
            state.group(1) if state else "not running"
        )
    return None


def _crash_looping_container(diagnostics: object) -> tuple[str, int] | None:
    """``(service, restarts)`` for a container that keeps coming back up."""
    text = str(diagnostics or "")
    if not text.strip():
        return None
    for marker in _ordered_markers(text):
        if str(marker.get("status")) in ("running", "restarting"):
            restarts = int(marker.get("restarts") or 0)
            if restarts >= _CRASH_LOOP_RESTARTS:
                return str(marker.get("service") or "backend"), restarts
    return None


def _is_atlas_deployment(
    preflight: Mapping[str, Any] | None,
    atlas: Mapping[str, Any] | None,
) -> bool:
    """True when the deployment's database is a MongoDB Atlas cluster."""
    info = dict(atlas or {})
    host = str((preflight or {}).get("host") or "")
    return bool(
        info.get("atlas") or is_atlas_host(host) or is_atlas_host(info.get("host"))
    )


def atlas_blocked_message(public_ip: object, *, configured: bool) -> str:
    """
    The exact operator-facing text for a blocked Atlas connection.

    The first three sentences are stable (they are what the deployment
    report shows for ``MONGODB_ATLAS_*``); the remainder adds the concrete
    address and what to configure.
    """
    address = str(public_ip or "").strip()
    message = (
        "MongoDB Atlas network access blocked the EC2 instance. "
        "CloudWise could not establish the backend database connection. "
        "Configure MongoDB Atlas Network Access or configure Atlas API "
        "credentials for automatic allowlisting."
    )
    if address:
        message += (
            f" Instance public IP: {address}; allow {address}/32 in "
            "MongoDB Atlas Network Access (never 0.0.0.0/0) and deploy again."
        )
    if not configured:
        message += (
            " MongoDB Atlas Network Access must allow the EC2 public IP. "
            "MONGODB_ATLAS_PUBLIC_KEY, MONGODB_ATLAS_PRIVATE_KEY and "
            "MONGODB_ATLAS_PROJECT_ID are not configured, so CloudWise "
            "could not add the /32 entry automatically."
        )
    return message


def _classify_database_response(
    backend_code: int | None,
    *,
    preflight: Mapping[str, Any] | None,
    atlas: Mapping[str, Any] | None,
    diagnostics: object,
    public_ip: str,
) -> tuple[str, str] | None:
    """
    Read the health endpoint's answer as a database diagnosis.

    The injected ``/api/health`` endpoint returns ``503`` **only** when the
    application cannot reach its database, so a 503 from the backend is
    direct evidence of a database problem (E/F). Anything else that is not
    a database declaration falls through to the caller.
    """
    if backend_code != 503:
        return None

    kind = str((preflight or {}).get("kind") or "")
    auth_failed, network_refused = _mongo_signals(diagnostics)
    info = dict(atlas or {})
    configured = bool(info.get("configured", atlas_configured()))

    if auth_failed and kind in ("", KIND_MONGODB):
        return ERROR_DATABASE_AUTH_FAILED, (
            "MongoDB authentication failed: the cluster rejected the "
            "credentials in the database environment variable "
            f"{info.get('envVar') or (preflight or {}).get('environmentVariable') or 'MONGO_URI'}. "
            "Check the username/password in the deployment environment "
            "(the connection string itself is never logged)."
        )

    if kind == KIND_MONGODB or network_refused or _is_atlas_deployment(
        preflight, atlas
    ):
        if _is_atlas_deployment(preflight, atlas):
            if configured:
                return ERROR_MONGODB_ATLAS_NETWORK_BLOCKED, atlas_blocked_message(
                    public_ip or info.get("publicIp") or "", configured=True
                )
            return ERROR_MONGODB_ATLAS_NOT_CONFIGURED, atlas_blocked_message(
                public_ip or info.get("publicIp") or "", configured=False
            )
        target = "MongoDB" if kind in ("", KIND_MONGODB) else kind
        return ERROR_DATABASE_CONNECTION_FAILED, (
            f"The application could not reach its {target} database: the "
            "health endpoint reports the database as unavailable. Verify "
            "the connection string value and that the database allows this "
            "instance's address."
        )

    if kind:
        return ERROR_DATABASE_CONNECTION_FAILED, (
            f"The application could not reach its {kind} database: the "
            "health endpoint reports the database as unavailable."
        )
    return ERROR_HEALTH_ENDPOINT_FAILED, (
        "The backend health endpoint returned HTTP 503 "
        "(service unavailable). Check the backend container logs for the "
        "underlying error."
    )


def classify_health_failure(
    *,
    health_message: str = "",
    split_report: Mapping[str, Any] | None = None,
    preflight: Mapping[str, Any] | None = None,
    app_port: int | None = None,
    diagnostics: str = "",
    atlas: Mapping[str, Any] | None = None,
    public_ip: str = "",
) -> tuple[str, str]:
    """
    Map a failed health check onto a specific error code.

    Returns ``(error_code, message)``; an empty ``error_code`` means "no
    specific diagnosis" and the caller keeps its existing generic failure
    handling untouched.

    ``diagnostics`` (the compose ``ps``/``logs`` output collected on the
    instance) and ``atlas`` (the Atlas allowlist report) are optional and
    only *sharpen* the diagnosis — without them the previous behaviour is
    reproduced exactly.
    """
    if preflight and preflight.get("status") == STATUS_FAILED:
        return (
            str(preflight.get("errorCode") or ERROR_DATABASE_CONNECTION_FAILED),
            str(preflight.get("message") or ""),
        )

    proxy = (preflight or {}).get("proxy")
    proxy_origin = str(proxy.get("origin") or "") if isinstance(proxy, Mapping) else ""

    split = split_report or {}
    backend_code, frontend_ok = _split_codes(split)
    unhealthy = split.get("status") == "FAILED"

    if unhealthy and diagnostics:
        # A — the instance never became usable.
        if _EC2_UNAVAILABLE_RE.search(str(diagnostics)):
            return ERROR_EC2_UNAVAILABLE, (
                "The EC2 instance is not in a running state, so nothing "
                "can be deployed to it. Check the instance in the EC2 "
                "console (state, stop protection, billing)."
            )
        # B — Docker itself is missing/down on the instance.
        if _DOCKER_UNAVAILABLE_RE.search(str(diagnostics)):
            return ERROR_DOCKER_UNAVAILABLE, (
                "Docker is not available on the EC2 instance "
                "(daemon not reachable or the CLI is missing), so the "
                "application containers cannot run. Check the instance "
                "bootstrap logs and the installed Docker packages."
            )

    if unhealthy and diagnostics:
        auth_failed, network_refused = _mongo_signals(diagnostics)
        stopped = _stopped_container(diagnostics)
        looping = _crash_looping_container(diagnostics)
        if (stopped is not None or looping is not None) and (
            auth_failed or network_refused
        ):
            # C caused by the database: report the root cause (E/F), not
            # merely "a container stopped".
            if stopped is not None:
                service, state = stopped
                state_text = f"stopped ({state})"
            else:
                service, restarts = looping or ("backend", 0)
                state_text = f"restarted {restarts} times"
            diagnosis = _classify_database_response(
                503,
                preflight=preflight,
                atlas=atlas,
                diagnostics=diagnostics,
                public_ip=public_ip,
            )
            if diagnosis is not None:
                code, message = diagnosis
                return code, f"The {service} container {state_text}. {message}"

    if unhealthy and diagnostics:
        looping = _crash_looping_container(diagnostics)
        if looping is not None:
            service, restarts = looping
            return ERROR_CONTAINER_FAILED, (
                f"The {service} container restarted {restarts} times and is "
                "not staying up. Read the container logs in this deployment "
                "for the startup error — the application never became "
                "reachable."
            )
        stopped = _stopped_container(diagnostics)
        if stopped is not None:
            service, state = stopped
            return ERROR_CONTAINER_FAILED, (
                f"The {service} container is not running ({state}). "
                "Read the container logs in this deployment for the exact "
                "startup error — the application never became reachable."
            )

    if unhealthy:
        if backend_code in (502, 504):
            if proxy_origin == "app":
                # The backend itself answered with 5xx — it is running, so
                # this is not a "backend down" diagnosis.
                return "", ""
            return ERROR_BACKEND_NOT_RUNNING, (
                f"The backend is not answering: nginx returned HTTP "
                f"{backend_code} while proxying to the backend port "
                "(upstream connection refused). The backend container "
                "likely crashed or is still starting — check the "
                "container logs in this deployment."
            )
        if backend_code in (0, None):
            return ERROR_NGINX_PROXY_FAILED, (
                "The nginx entry point did not answer for the API path "
                f"({health_message or 'no response'}). The router container "
                "is not listening or the API route is not configured."
            )
        if not frontend_ok:
            return ERROR_FRONTEND_FAILED, (
                f"The frontend route did not answer correctly "
                f"({health_message or 'no response'}). Check the frontend "
                "container logs and the build output."
            )
        # H (and E/F): the backend answered — read what it said.
        database_diagnosis = _classify_database_response(
            backend_code,
            preflight=preflight,
            atlas=atlas,
            diagnostics=diagnostics,
            public_ip=public_ip,
        )
        if database_diagnosis is not None:
            return database_diagnosis
        if backend_code is not None and not _response_ok(backend_code):
            return ERROR_HEALTH_ENDPOINT_FAILED, (
                f"The backend health endpoint returned HTTP {backend_code} "
                f"for the API path ({health_message or 'no detail'}). The "
                "application is reachable but not healthy — check the "
                "backend container logs."
            )
        return "", ""

    code = _http_code(health_message)
    if code in (502, 504):
        return ERROR_BACKEND_NOT_RUNNING, (
            f"The application returned HTTP {code}: the process behind "
            "nginx is not accepting connections."
        )

    # No usable HTTP code: only claim "nothing is listening" when the
    # message actually smells like a connection problem. Anything else
    # keeps the existing generic health-check failure untouched.
    text = str(health_message or "").lower()
    connectivity_hint = any(
        token in text
        for token in (
            "refused",
            "timed out",
            "timeout",
            "000",
            "connection",
            "unreachable",
            "no route",
        )
    )
    if code in (0, None) and (code == 0 or connectivity_hint):
        if int(app_port or 0) in (80, 443):
            return ERROR_NGINX_PROXY_FAILED, (
                f"Nothing answered on port {app_port} — the nginx entry "
                "point is not running."
            )
        return ERROR_BACKEND_NOT_RUNNING, (
            f"The application port {app_port or 'unknown'} is closed: the "
            "application process is not running."
        )
    return "", ""


def classify_backend_start_failure(
    diagnostics: object,
    *,
    atlas: Mapping[str, Any] | None = None,
    public_ip: str = "",
    backend_port: int | None = None,
) -> tuple[str, str]:
    """
    Read the backend container's state and logs when it never starts.

    Used by the backend service gate, which runs *after* ``docker compose
    up`` and *before* any HTTP probe: there is no response to classify yet,
    only the container state, the restart counter and the last log lines.

    Returns ``(error_code, message)``. Both are empty when the evidence does
    not prove a failure (the container is up and simply still starting), so
    the caller must leave the existing health check in charge instead of
    inventing a failure.
    """
    text = str(diagnostics or "")
    verdict = gate_result(text)

    # 1) The database is the root cause whenever the driver says so — the
    #    container dying is only the symptom.
    auth_failed, network_refused = _mongo_signals(text)
    if auth_failed or network_refused:
        diagnosis = _classify_database_response(
            503,
            preflight=None,
            atlas=atlas,
            diagnostics=text,
            public_ip=public_ip,
        )
        if diagnosis is not None:
            return diagnosis

    # 2) The container is not running at all (markers or compose ps).
    stopped = _stopped_container(text)
    if stopped is not None:
        service, state = stopped
        return ERROR_CONTAINER_FAILED, (
            f"The {service} container is not running ({state}). Read the "
            "container logs in this deployment for the exact startup error "
            "— the application never became reachable."
        )

    # 3) It keeps being restarted instead of staying up.
    looping = _crash_looping_container(text)
    if looping is not None:
        service, restarts = looping
        return ERROR_CONTAINER_FAILED, (
            f"The {service} container restarted {restarts} times and is not "
            "staying up. Read the container logs in this deployment for the "
            "startup error — the application never became reachable."
        )

    # 4) The gate itself observed the container die between two samples.
    if verdict in ("exited", "dead", "created", "crashloop"):
        return ERROR_CONTAINER_FAILED, (
            f"The backend container did not stay up (startup gate: "
            f"{verdict}). Read the container logs in this deployment for "
            "the exact startup error."
        )

    # 5) Nothing proves a failure: the process may just still be starting,
    #    the service may be named differently, or Docker may be unavailable.
    return "", ""
