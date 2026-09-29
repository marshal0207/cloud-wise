"""
Deployment adapter for repositories with a separate frontend/ + backend/
layout (the ``separate_frontend_backend`` architecture).

The adapter renders the four deployment artefacts for that architecture:

* ``frontend/Dockerfile``  — multi-stage static build (nginx) or SSR runtime
* ``backend/Dockerfile``   — runtime image with the detected port + CMD
* ``docker-compose.yml``   — frontend + backend + router nginx (no database)
* ``nginx.conf``           — routes ``/api`` to the backend, ``/`` to the
  frontend, keeping the API same-origin for the browser

The result dict uses exactly the same keys as
``api.services.deployment_file_generator.generate_deployment_files`` so the
existing views/pipeline consume it unchanged. Extra split-only fields are
added *inside* ``deploymentPlan`` (architecture, manifest, backendPort,
apiProbePaths, ...) and never replace existing keys.
"""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import asdict
from typing import Any, Mapping, Sequence

from ...tech_stack_detector import TechStack
from ...deployment_file_generator import (
    _find_cicd,
    _find_compose,
    _find_dockerfile,
    build_deployment_plan,
    format_detection,
    generate_aws_github_actions,
    generate_dockerfile,
    generate_nginx_conf,
    parse_exposed_port_from_dockerfile,
)
from ..repository_detector.models import RepositoryProfile
from ..mongodb_atlas_service import find_database_env_var

PUBLISHED_PORT = 80

# dev-only tools that must stay installed when the start script needs them.
_RUNTIME_NODE_DEV_TOOLS = ("nodemon", "ts-node", "tsx ", "next dev")

_PRODUCTION_FLAGS = {
    "npm": "--omit=dev",
    "pnpm": "--prod",
    "yarn": "--production",
    "bun": "--omit=dev",
}


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

def _cmd_json(command: str | None) -> str:
    """Render a Dockerfile CMD/ENTRYPOINT JSON array for ``command``."""
    command = (command or "").strip()
    if not command:
        return '["true"]'
    # Shell syntax cannot be expressed as an exec-form argv — use /bin/sh.
    if re.search(r"[|&;<>()$`\\\n]", command):
        return json.dumps(["/bin/sh", "-c", command])
    argv = shlex.split(command)
    if not argv:
        return '["true"]'
    return json.dumps(argv)


def _production_install(command: str | None, package_manager: str) -> str:
    """Append the production flag to a node install command."""
    if not command:
        return command or ""
    flag = _PRODUCTION_FLAGS.get(package_manager)
    if not flag or flag in command:
        return command
    return f"{command} {flag}"


def _needs_runtime_dev_deps(start_script: str | None) -> bool:
    lowered = (start_script or "").lower()
    return any(tool in lowered for tool in _RUNTIME_NODE_DEV_TOOLS)


def _env_arg_lines(names: Sequence[str]) -> tuple[str, str]:
    """Dockerfile ``ARG``/``ENV`` lines for build-time frontend variables."""
    if not names:
        return "", ""
    args = "\n".join(f"ARG {name}" for name in names)
    envs = "\n".join(f"ENV {name}=${{{name}}}" for name in names)
    return f"{args}\n", f"{envs}\n"


# ---------------------------------------------------------------------------
# Dockerfiles
# ---------------------------------------------------------------------------

def render_frontend_dockerfile(profile: RepositoryProfile) -> str:
    """Dockerfile for the profiled frontend (static SPA or SSR runtime)."""
    frontend = profile.frontend
    if frontend is None:
        raise ValueError("Frontend profile required for the frontend Dockerfile")
    package_manager = frontend.package_manager or "npm"
    install = frontend.install_command or f"{package_manager} install"
    build = frontend.build_command or f"{package_manager} run build"
    copy_deps = (
        "COPY package*.json ./" if package_manager == "npm" else "COPY . ."
    )
    arg_block, env_block = _env_arg_lines(frontend.build_time_env)

    if frontend.framework == "nextjs":
        # SSR application — the container itself serves the app.
        return f"""FROM node:20-alpine
WORKDIR /app
{arg_block}{copy_deps}
RUN {install}
COPY . .
{env_block}ENV NEXT_TELEMETRY_DISABLED=1 NODE_ENV=production PORT={frontend.port}
RUN {build}
EXPOSE {frontend.port}
CMD {_cmd_json(frontend.start_command or f"{package_manager} start")}
"""

    output_dir = frontend.output_directory or "dist"
    # SPA fallback so client-side routes (/doctors, /booking, ...) resolve.
    # Literal "\n" escapes keep the RUN instruction on a single Dockerfile
    # line; printf expands them when the image is built.
    #
    # The deny locations use the same rules as the router nginx (see
    # deployment_file_generator._SENSITIVE_PATH_RULES). printf consumes one
    # level of backslashes, so '\\\\.' here reaches nginx as '\.'.
    spa_conf = (
        r"server {\n"
        r"    listen 80;\n"
        r"    server_name _;\n"
        r"    root /usr/share/nginx/html;\n"
        r"    index index.html;\n"
        r"\n"
        r'    location ~* "\\.env($|\\.)" { return 404; }\n'
        r'    location ~* "\\.git(/|$)" { return 404; }\n'
        r'    location ~* "/\\.(ssh|aws|docker|npmrc|netrc|htpasswd)" { return 404; }\n'
        r'    location ~* "/(id_rsa|id_dsa|id_ecdsa|id_ed25519)(\\.[^/]*)?$" { return 404; }\n'
        r'    location ~* "\\.(pem|key|p12|pfx)$" { return 404; }\n'
        r"\n"
        r"    location / {\n"
        r"        try_files $uri $uri/ /index.html;\n"
        r"    }\n"
        r"}\n"
    )
    return f"""FROM node:20-alpine AS builder
WORKDIR /app
{arg_block}{copy_deps}
RUN {install}
COPY . .
{env_block}RUN {build}

FROM nginx:alpine
COPY --from=builder /app/{output_dir} /usr/share/nginx/html
RUN printf '{spa_conf}' > /etc/nginx/conf.d/default.conf
EXPOSE {frontend.port}
CMD ["nginx", "-g", "daemon off;"]
"""


def render_backend_dockerfile(
    profile: RepositoryProfile,
    *,
    files: Mapping[str, str],
    package_managers: Sequence[str] | None = None,
) -> str:
    """Dockerfile for the profiled backend (node / python / java)."""
    backend = profile.backend
    if backend is None:
        raise ValueError("Backend profile required for the backend Dockerfile")
    port = backend.port or 8000

    if backend.runtime == "java":
        manifest = (backend.manifest_path or "").lower()
        if "gradle" in manifest or "gradle" in (package_managers or []):
            build_tool = "GRADLE"
        else:
            build_tool = "MAVEN"
        return generate_dockerfile(TechStack("SPRING_BOOT", build_tool, port))

    if backend.runtime == "python":
        return _python_backend_dockerfile(profile, files=files, port=port)

    # Node.js (and unknown runtimes that fall back to a node runtime).
    package_manager = backend.package_manager or "npm"
    install = backend.install_command or f"{package_manager} install"
    if not _needs_runtime_dev_deps(backend.start_script):
        install = _production_install(install, package_manager)
    copy_deps = (
        "COPY package*.json ./" if package_manager == "npm" else "COPY . ."
    )
    return f"""FROM node:20-alpine
WORKDIR /app
{copy_deps}
RUN {install}
COPY . .
ENV NODE_ENV=production PORT={port}
EXPOSE {port}
CMD {_cmd_json(backend.start_command or f"{package_manager} start")}
"""


def _python_backend_dockerfile(
    profile: RepositoryProfile, *, files: Mapping[str, str], port: int,
) -> str:
    """Dockerfile for a Python backend (Django / Flask / plain)."""
    backend = profile.backend
    if backend is None:
        raise ValueError("Backend profile required for the backend Dockerfile")
    prefix = f"{backend.path}/"
    scoped_names = {
        str(key).replace("\\", "/")[len(prefix):].lower()
        for key in files
        if str(key).replace("\\", "/").startswith(prefix)
    }
    has_requirements = "requirements.txt" in scoped_names
    has_pyproject = "pyproject.toml" in scoped_names

    start_command = backend.start_command or ""
    needs_gunicorn = start_command.startswith("gunicorn")
    extra = " gunicorn" if needs_gunicorn else ""

    if has_requirements:
        steps = (
            "COPY requirements.txt ./\n"
            f"RUN pip install --no-cache-dir -r requirements.txt{extra}\n"
            "COPY . ."
        )
    elif has_pyproject:
        steps = f"COPY . .\nRUN pip install --no-cache-dir .{extra}"
    else:
        steps = "COPY . ."

    return f"""FROM python:3.13-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
{steps}
EXPOSE {port}
CMD {_cmd_json(backend.start_command)}
"""


# ---------------------------------------------------------------------------
# Compose + nginx
# ---------------------------------------------------------------------------

def render_split_compose(
    profile: RepositoryProfile,
    *,
    backend_port: int,
    env_vars: Sequence[str] | None = None,
) -> str:
    """Compose file for the split architecture (no database containers)."""
    frontend = profile.frontend
    backend = profile.backend
    if frontend is None or backend is None:
        raise ValueError("Split profiles required for the compose file")

    build_args = list(frontend.build_time_env)
    if build_args:
        arg_lines = "\n".join(
            f"        - {name}=${{{name}:-}}" for name in build_args
        )
        frontend_build_block = (
            f"      args:\n{arg_lines}\n    restart: unless-stopped"
        )
    else:
        frontend_build_block = "    restart: unless-stopped"

    backend_environment = [f"      - PORT={backend_port}"]
    for name in env_vars or []:
        if str(name).strip().upper() == "PORT":
            # PORT already carries the detected port; a ``${PORT}``
            # passthrough would win in compose (later entries override) and
            # could send the container to a port nginx never proxies to.
            continue
        backend_environment.append(f"      - {name}=${{{name}}}")
    backend_env_block = "\n".join(backend_environment)

    frontend_context = f"./{frontend.path}"
    backend_context = f"./{backend.path}"

    return f"""version: '3.8'

services:
  frontend:
    build:
      context: {frontend_context}
{frontend_build_block}
    environment:
      - NODE_ENV=production
  backend:
    build:
      context: {backend_context}
    restart: unless-stopped
    environment:
{backend_env_block}
  nginx:
    image: nginx:alpine
    ports:
      - "{PUBLISHED_PORT}:{PUBLISHED_PORT}"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
    depends_on:
      - frontend
      - backend
    restart: unless-stopped
"""


# ---------------------------------------------------------------------------
# Readiness gate (views pre-flight)
# ---------------------------------------------------------------------------

def readiness_problem(deployment_plan: Mapping | None) -> str | None:
    """
    Actionable error when a split repository cannot be deployed at all.

    Returns ``None`` for every healthy plan and for non-split plans (the
    legacy flow handles those without this gate).
    """
    plan = deployment_plan or {}
    if plan.get("architecture") != "separate_frontend_backend":
        return None

    backend = (plan.get("manifest") or {}).get("backend") or {}
    backend_path = backend.get("path") or "backend"

    if not backend.get("startCommand"):
        return (
            f"Backend directory '{backend_path}' has no runnable start "
            f"command. Add a \"scripts.start\" entry to "
            f"'{backend_path}/package.json' (or an entry file such as "
            f"server.js / app.py / manage.py) so CloudWise can start it."
        )
    if not backend.get("port"):
        return (
            f"Backend port for '{backend_path}' could not be detected. Add "
            f"PORT=<port> to .env.example, expose it in "
            f"'{backend_path}/Dockerfile', or document it as "
            f"localhost:<port> in the README."
        )
    return None


# ---------------------------------------------------------------------------
# Database readiness endpoint (/api/health)
# ---------------------------------------------------------------------------

HEALTH_PATH = "/api/health"

_MONGODB_ENV_NAMES = (
    "MONGO_URI",
    "MONGODB_URI",
    "MONGO_URL",
    "MONGO_CONNECTION_URI",
    "MONGO_DB_URI",
    "MONGODB_URL",
)

_APP_VAR_RE = re.compile(
    r"(?m)^[ \t]*(?:const|let|var)[ \t]+([A-Za-z_$][\w$]*)[ \t]*=[ \t]*"
    r"(?:express[ \t]*\(|require\([ \t]*['\"]express['\"]\s*\)[ \t]*\()"
)
_MONGOOSE_RE = re.compile(
    r"require\([ \t]*['\"]mongoose['\"]\)|from[ \t]*['\"]mongoose['\"]"
    r"|mongoose\.connect",
)
_MONGODB_DRIVER_RE = re.compile(
    r"require\([ \t]*['\"]mongodb['\"]\)|from[ \t]*['\"]mongodb['\"]"
    r"|MongoClient",
)
_DB_ENV_REFERENCE_RE = re.compile(
    r"process\.env\.([A-Z][A-Z0-9_]{2,})|process\.env\[[\w'\"]+\]"
)


def detect_express_app_var(source: str) -> str:
    """Name of the Express app instance (``app`` when clearly used)."""
    match = _APP_VAR_RE.search(str(source or ""))
    if match:
        return match.group(1)
    if re.search(r"(?m)^[ \t]*app\.listen\s*\(", str(source or "")):
        return "app"
    return ""


def detect_database_driver(sources: Sequence[str]) -> str:
    """``mongoose`` / ``mongodb`` / ``""`` — which driver the app uses."""
    text = "\n".join(str(source or "") for source in sources)
    if _MONGOOSE_RE.search(text):
        return "mongoose"
    if _MONGODB_DRIVER_RE.search(text):
        return "mongodb"
    return ""


def _health_snippet(app_var: str, driver: str, env_var: str) -> str:
    """The injected handler — never exposes a URI, credential or traceback."""
    if driver == "mongodb":
        check = f"""  try {{
    const uri = process.env['{env_var or "MONGO_URI"}'] || ''
    if (uri) {{
      const {{ MongoClient }} = require('mongodb')
      const client = new MongoClient(uri, {{ serverSelectionTimeoutMS: 1500 }})
      await client.connect()
      connected = true
      await client.close()
    }}
  }} catch (error) {{
    connected = false
  }}"""
    else:
        check = """  try {
    connected = require('mongoose').connection.readyState === 1
  } catch (error) {
    connected = false
  }"""
    return (
        "// CloudWise: database readiness endpoint (added at deploy time).\n"
        "// HTTP 200 only while the database connection is established; the\n"
        "// response never contains a connection string, credential or stack\n"
        "// trace.\n"
        f"{app_var}.get('{HEALTH_PATH}', async (request, response) => {{\n"
        "  let connected = false\n"
        f"{check}\n"
        "  if (!connected) {\n"
        "    return response.status(503).json("
        "{ status: 'unhealthy', database: 'unavailable' })\n"
        "  }\n"
        "  return response.status(200).json("
        "{ status: 'ok', database: 'connected' })\n"
        "})\n"
    )


def install_database_health_route(
    source: str,
    *,
    app_var: str,
    driver: str,
    env_var: str = "",
) -> tuple[str, str]:
    """
    Make ``GET /api/health`` report database readiness.

    Returns ``(new_source, status)`` with ``status`` one of:

    * ``injected``       — the handler was added (or replaces a naive one)
    * ``already_present``— the repository already reports DB readiness
    * ``skipped``        — nothing safe to do; existing behaviour kept

    The handler is registered on the *same* Express instance and before any
    existing ``/api/health`` handler, so Express answers with the
    database-aware response. No existing route is touched or removed.
    """
    text = str(source or "")
    if not text.strip() or not app_var:
        return source, "skipped"

    snippet = _health_snippet(app_var, driver, env_var)
    existing = re.search(
        r"(?m)^(?P<indent>[ \t]*)(?P<recv>[A-Za-z_$][\w$.]*)\.(?:get|use)"
        r"[ \t]*\([ \t]*['\"]" + re.escape(HEALTH_PATH) + r"['\"]",
        text,
    )
    if existing is not None:
        # The repository already answers the endpoint: only take over when
        # it clearly does not check the database.
        if "readyState" in text or "database" in text[existing.start():]:
            return source, "already_present"
        if existing.group("recv") != app_var:
            return source, "skipped"
        at = existing.start()
        return text[:at] + snippet + "\n" + text[at:], "injected"

    anchor = re.search(
        rf"(?m)^[ \t]*{re.escape(app_var)}\.listen[ \t]*\(", text
    )
    if anchor is not None:
        at = anchor.start()
        return text[:at] + snippet + "\n" + text[at:], "injected"
    return text.rstrip("\n") + "\n\n" + snippet, "injected"


# ---------------------------------------------------------------------------
# nginx upstream stability (no container IPs, no stale DNS)
# ---------------------------------------------------------------------------

# `proxy_pass http://service[:port];` — a *literal* upstream is resolved by
# nginx once, at config load, and then cached forever. Docker container IPs
# change whenever a container is recreated, which is exactly how a running
# nginx ends up proxying to a dead address.
_PROXY_PASS_LINE_RE = re.compile(
    r"^(?P<indent>[ \t]*)proxy_pass[ \t]+"
    r"(?P<url>https?://(?P<host>[A-Za-z0-9][A-Za-z0-9._-]*)(?::(?P<port>\d+))?)"
    r"[ \t]*;(?P<ending>\r?\n)?$"
)
_IPV4_HOST_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")
_RESOLVER_RE = re.compile(r"(?m)^[ \t]*resolver[ \t]+")
_SERVER_BLOCK_RE = re.compile(r"^[ \t]*server[ \t]*\{")

DOCKER_DNS_RESOLVER = "resolver 127.0.0.11 valid=10s ipv6=off;"


def stabilize_nginx_conf(text: str) -> tuple[str, dict[str, Any]]:
    """
    Re-resolve compose service names on every request.

    ``proxy_pass http://backend:5000;`` is rewritten to a variable-backed
    upstream plus Docker's embedded DNS resolver, so the *service name*
    keeps working after the backend container is recreated with a new IP.
    Nothing is hard-coded: the host stays the Compose service name, and a
    config that already uses a variable, an IP address or a proxied URI is
    left untouched.
    """
    report: dict[str, Any] = {
        "changed": False,
        "upstreams": 0,
        "resolverAdded": False,
        "reason": "",
    }
    content = str(text or "")
    if "proxy_pass" not in content:
        report["reason"] = "no_proxy_pass"
        return text, report

    lines = content.splitlines(keepends=True)
    out: list[str] = []
    rewritten = 0
    for line in lines:
        match = _PROXY_PASS_LINE_RE.match(line)
        if match is None:
            out.append(line)
            continue
        host = match.group("host")
        if _IPV4_HOST_RE.match(host) or "$" in line:
            # An IP address needs no DNS; a variable is already dynamic.
            out.append(line)
            continue
        indent = match.group("indent") or ""
        ending = match.group("ending") or "\n"
        out.append(f"{indent}set $cloudwise_upstream {match.group('url')};{ending}")
        out.append(f"{indent}proxy_pass $cloudwise_upstream;{ending}")
        rewritten += 1

    if rewritten == 0:
        report["reason"] = "no_literal_upstream"
        return text, report

    if _RESOLVER_RE.search("".join(out)) is None:
        for index, line in enumerate(out):
            if _SERVER_BLOCK_RE.match(line):
                ending = "\n" if line.endswith("\n") else ""
                out.insert(index + 1, f"    {DOCKER_DNS_RESOLVER}{ending}")
                report["resolverAdded"] = True
                break

    report["changed"] = True
    report["upstreams"] = rewritten
    return "".join(out), report


# ---------------------------------------------------------------------------
# Compose environment wiring (the backend must receive the database URI)
# ---------------------------------------------------------------------------

def ensure_backend_env_vars(
    compose_text: str,
    names: Sequence[str],
) -> tuple[str, dict[str, Any]]:
    """
    Guarantee ``- <VAR>=${<VAR>}`` for each name in the ``backend`` service.

    A repository that reads ``process.env.MONGO_URI`` but whose compose file
    never forwards the variable silently falls back to in-memory data — and
    the deployment then fails with a confusing health error. Only additive
    list entries are inserted (never a rewrite of the file), and anything
    that cannot be done safely is reported instead of guessed at.
    """
    report: dict[str, Any] = {"injected": [], "skipped": [], "present": []}
    wanted = [str(name) for name in names if str(name).strip()]
    content = str(compose_text or "")
    if not wanted or not content.strip():
        return compose_text, report

    lines = content.splitlines(keepends=True)
    start = None
    for index, line in enumerate(lines):
        if re.match(r"^ {2}backend:[ \t]*(#.*)?$", line):
            start = index
            break
    if start is None:
        report["skipped"] = list(wanted)
        report["reason"] = "no_backend_service"
        return compose_text, report

    end = len(lines)
    for index in range(start + 1, len(lines)):
        if re.match(r"^ {2}\S", lines[index]):
            end = index
            break

    block = "".join(lines[start:end])
    missing = [
        name for name in wanted
        if not re.search(rf"\b{re.escape(name)}\b", block)
    ]
    report["present"] = [name for name in wanted if name not in missing]
    if not missing:
        return compose_text, report

    env_index = None
    env_kind = ""
    for index in range(start, end):
        match = re.match(r"^ {4}environment:[ \t]*(?P<rest>.*)$", lines[index])
        if match:
            env_index = index
            env_kind = "list" if not match.group("rest").strip("# \t") else "inline"
            break

    items = [f"      - {name}=${{{name}}}\n" for name in missing]

    if env_index is None:
        insert_at = end
        while insert_at - 1 > start and not lines[insert_at - 1].strip():
            insert_at -= 1
        lines[insert_at:insert_at] = ["    environment:\n", *items]
        report["injected"] = list(missing)
        return "".join(lines), report

    if env_kind == "inline":
        rest = lines[env_index].split("environment:", 1)[1].strip()
        if rest.rstrip() not in ("{}", ""):
            report["skipped"] = list(missing)
            report["reason"] = "mapping_environment"
            return compose_text, report
        lines[env_index] = "    environment:\n"
        lines[env_index + 1:env_index + 1] = items
        report["injected"] = list(missing)
        return "".join(lines), report

    boundary = env_index + 1
    while boundary < end:
        line = lines[boundary]
        if line.strip() and re.match(r"^ {4}\S", line):
            break
        if line.strip() and re.match(r"^ {6}[\w'\"]+\s*:", line):
            # mapping-style environment entries: mixing styles is invalid
            report["skipped"] = list(missing)
            report["reason"] = "mapping_environment"
            return compose_text, report
        boundary += 1
    lines[boundary:boundary] = items
    report["injected"] = list(missing)
    return "".join(lines), report


def _backend_sources(
    profile: RepositoryProfile, files: Mapping[str, str]
) -> list[str]:
    """Every file that belongs to the backend service."""
    backend = profile.backend
    if backend is None:
        return []
    prefix = f"{str(backend.path).strip('/')}/".lower()
    return [
        str(content)
        for key, content in files.items()
        if str(key).replace("\\", "/").lower().startswith(prefix)
    ]


def _backend_entry_file(
    profile: RepositoryProfile, files: Mapping[str, str]
) -> str:
    """Repo-relative path of the Node entry file, or ``""``."""
    backend = profile.backend
    if backend is None:
        return ""
    candidates: list[str] = []
    if backend.entry_file:
        candidates.append(f"{str(backend.path).strip('/')}/{backend.entry_file}")
    candidates.extend(
        f"{str(backend.path).strip('/')}/{name}"
        for name in ("server.js", "app.js", "index.js")
    )
    lowered = {str(key).replace("\\", "/").lower(): str(key) for key in files}
    for candidate in candidates:
        key = candidate.replace("\\", "/")
        if key in files:
            return key
        match = lowered.get(key.lower())
        if match:
            return match
    return ""


def _resolve_database_env_var(
    profile: RepositoryProfile,
    files: Mapping[str, str],
    env_vars: Sequence[str],
) -> str:
    """
    Name of the variable that carries this repository's database URI.

    Prefers a required variable the repository itself declares, then any
    conventional MongoDB name the repository references. ``""`` means "no
    database variable could be identified" — nothing is guessed.
    """
    if not profile.database_type and not profile.required_env_vars:
        return ""
    for name in profile.required_env_vars or ():
        if str(name).strip() in _MONGODB_ENV_NAMES:
            return str(name).strip()
    return find_database_env_var(
        {str(name): "" for name in env_vars or ()}, files=files
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def generate_split_deployment(
    files: Mapping[str, str],
    profile: RepositoryProfile,
    *,
    analysis: Mapping,
    stack: Any | None = None,
    provider: str = "AWS",
    tree: list[dict] | None = None,
) -> dict[str, object]:
    """
    Render deployment files for a ``separate_frontend_backend`` repository.

    Returns the same result shape as
    ``generate_deployment_files`` (technology / *_preserved / port / files /
    detection / analysis / deploymentPlan). Existing user-authored Dockerfile,
    compose and nginx files are preserved, never overwritten.
    """
    env_vars = list((analysis.get("environmentVariables") or []))
    package_managers = list((analysis.get("packageManagers") or []))
    frontend = profile.frontend
    backend = profile.backend
    if frontend is None or backend is None:
        raise ValueError(
            "generate_split_deployment requires a separate_frontend_backend "
            "profile with both a frontend and a backend"
        )

    generated: dict[str, str] = {}
    dockerfile_preserved = False
    compose_preserved = False

    # ---- frontend/Dockerfile ----
    frontend_key = f"{frontend.path}/Dockerfile"
    existing_frontend = _find_dockerfile(files, frontend.path)
    if existing_frontend and files[existing_frontend].strip():
        generated[frontend_key] = files[existing_frontend]
        dockerfile_preserved = True
        frontend_port = parse_exposed_port_from_dockerfile(
            files[existing_frontend], default_port=frontend.port,
        )
    else:
        generated[frontend_key] = render_frontend_dockerfile(profile)
        frontend_port = frontend.port

    # ---- backend/Dockerfile ----
    backend_key = f"{backend.path}/Dockerfile"
    detected_backend_port = backend.port or 8000
    existing_backend = _find_dockerfile(files, backend.path)
    if existing_backend and files[existing_backend].strip():
        generated[backend_key] = files[existing_backend]
        dockerfile_preserved = True
        backend_port = parse_exposed_port_from_dockerfile(
            files[existing_backend], default_port=detected_backend_port,
        )
    else:
        generated[backend_key] = render_backend_dockerfile(
            profile, files=files, package_managers=package_managers,
        )
        backend_port = detected_backend_port

    # ---- docker-compose.yml ----
    compose_key = _find_compose(files)
    if compose_key and files[compose_key].strip():
        generated["docker-compose.yml"] = files[compose_key]
        compose_preserved = True
    else:
        generated["docker-compose.yml"] = render_split_compose(
            profile, backend_port=backend_port, env_vars=env_vars,
        )

    # ---- nginx.conf ----
    existing_nginx = next(
        (
            key for key in files
            if str(key).replace("\\", "/").lower() == "nginx.conf"
        ),
        None,
    )
    if existing_nginx and files[existing_nginx].strip():
        generated["nginx.conf"] = files[existing_nginx]
    else:
        generated["nginx.conf"] = generate_nginx_conf(
            frontend_port, backend_port,
        )

    # ---- AWS CI/CD pipeline (unchanged behaviour) ----
    cicd_key = _find_cicd(files)
    cicd_preserved = False
    if cicd_key and files[cicd_key].strip():
        generated[cicd_key] = files[cicd_key]
        generated[".github/workflows/deploy.yml"] = files[cicd_key]
        cicd_preserved = True
    else:
        cicd_content = generate_aws_github_actions(PUBLISHED_PORT, provider)
        generated[".github/workflows/deploy.yml"] = cicd_content
        generated[".github/workflows/aws-deploy.yml"] = cicd_content

    # ---- database wiring: env var, readiness endpoint, stable upstreams ----
    # Three failures used to look identical from the outside ("health check
    # failed"): the backend never receiving its connection string, no
    # endpoint that reports database readiness, and nginx caching the
    # backend's container IP after it was recreated. Each is fixed here,
    # additively, without touching the architecture.
    database_env_var = _resolve_database_env_var(profile, files, env_vars)
    compose_text, compose_env_report = ensure_backend_env_vars(
        generated["docker-compose.yml"],
        [database_env_var] if database_env_var else [],
    )
    generated["docker-compose.yml"] = compose_text

    nginx_text, nginx_report = stabilize_nginx_conf(generated["nginx.conf"])
    # Only CloudWise-generated configs are post-processed here: a repository's
    # own nginx.conf is preserved byte-for-byte (secret-path denial is built
    # into generate_nginx_conf, and the frontend container gets its own).
    generated["nginx.conf"] = nginx_text

    health_status = "unavailable"
    health_file = ""
    if (profile.backend is not None and profile.backend.runtime == "node") or (
        profile.database_type
    ):
        entry_rel = _backend_entry_file(profile, files)
        sources = _backend_sources(profile, files)
        driver = detect_database_driver(sources)
        app_var = detect_express_app_var(files.get(entry_rel, "")) if entry_rel else ""
        if entry_rel and app_var and driver:
            patched, health_status = install_database_health_route(
                files[entry_rel],
                app_var=app_var,
                driver=driver,
                env_var=database_env_var,
            )
            if health_status == "injected":
                generated[entry_rel] = patched
                health_file = entry_rel

    # ---- deployment plan ----
    deployment_plan = build_deployment_plan(
        generated_files=generated,
        analysis=analysis,
        containers=["frontend", "backend", "nginx"],
        ports=[PUBLISHED_PORT],
        requires_nginx=True,
    )
    probe_paths = list(profile.api_probe_paths)
    if health_status in ("injected", "already_present") and (
        HEALTH_PATH not in probe_paths
    ):
        # Probe the endpoint that actually reports database readiness.
        probe_paths = [HEALTH_PATH, *probe_paths]
    deployment_plan.update({
        "architecture": profile.architecture,
        "manifest": profile.to_manifest(),
        "frontendPort": frontend_port,
        "backendPort": backend_port,
        "portEvidence": backend.port_evidence,
        "apiBasePaths": list(profile.api_base_paths),
        "apiProbePaths": probe_paths,
        "issues": list(profile.issues),
        "databaseEnvVar": database_env_var,
        "healthEndpoint": (
            HEALTH_PATH if health_status in ("injected", "already_present") else ""
        ),
        "healthEndpointInjected": health_status == "injected",
        "healthEndpointFile": health_file,
        "backendEnvInjection": compose_env_report,
        "nginxUpstreamsStable": bool(nginx_report.get("changed"))
        or not bool(nginx_report.get("upstreams")),
        "nginxSensitivePathsDenied": "cloudwise-deny-sensitive-paths"
        in generated["nginx.conf"],
    })

    return {
        "technology": asdict(stack) if stack is not None else None,
        "dockerfile_preserved": dockerfile_preserved,
        "compose_preserved": compose_preserved,
        "cicd_preserved": cicd_preserved,
        "port": PUBLISHED_PORT,
        "files": generated,
        "detection": format_detection(analysis),
        "analysis": analysis,
        "deploymentPlan": deployment_plan,
    }
