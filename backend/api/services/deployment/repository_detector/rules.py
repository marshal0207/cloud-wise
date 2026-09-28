"""
Detection rules for the additive deployment adaptation layer.

Only the structural facts needed by the split-architecture adapter are
derived here:

* service directories (the decision-layer gate),
* per-service package manager, install/build/start commands,
* backend port with explicit evidence,
* frontend API paths used for same-origin routing and live verification.

The service-directory gate deliberately reuses
``api.services.deployment_file_generator._resolve_service_directories`` so a
repository is routed to the new adapter only when the existing CloudWise
split-layout branch would have been taken as well. Every other repository
falls through to the untouched legacy code path.
"""

from __future__ import annotations

import json
import re
from typing import Mapping

from ...tech_stack_detector import (
    BACKEND_DIRECTORIES,
    BACKEND_MARKER_FILENAMES,
    ENV_TEMPLATE_FILENAMES,
    FRONTEND_DIRECTORIES,
    _backend_default_port,
    _package_dependencies,
    _resolve_frontend_framework,
    detect_environment_variables,
)
from ...deployment_file_generator import _resolve_service_directories
from .models import BackendProfile, FrontendProfile

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NODE_ENTRY_FILES = ("server.js", "index.js", "app.js", "main.js")
PYTHON_ENTRY_FILES = ("app.py", "main.py", "wsgi.py", "asgi.py")
DOCKERFILE_BASENAMES = ("dockerfile", "dockerfile.prod", "dockerfile.dev")

_FRONTEND_FRAMEWORK_SLUGS = {
    "Next.js": "nextjs",
    "Vite": "vite",
    "CRA": "cra",
    "Vue": "vue",
    "Angular": "angular",
}

_FRONTEND_ENV_PREFIXES = ("VITE_", "REACT_APP_", "NEXT_PUBLIC_", "VUE_APP_")

_CODE_SUFFIXES = (
    ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".py", ".java", ".go", ".rb", ".php", ".vue", ".svelte", ".html",
)

_SPA_ROUTE_PATTERN = re.compile(r"""path\s*=\s*["'](/[^"']*)["']""")
_API_PATH_PATTERN = re.compile(
    r"""["'`]((?:https?://[^"'`\s]+)?/?api/[A-Za-z0-9_.\-/]*)["'`]"""
)
_EXPOSE_PATTERN = re.compile(
    r"^\s*EXPOSE\s+(\d{2,5})\s*$", re.IGNORECASE | re.MULTILINE,
)
_ENV_PORT_PATTERN = re.compile(
    r"^\s*(?:-\s*)?PORT\s*=\s*(\d{2,5})\s*(?:#.*)?$", re.MULTILINE,
)
_LOCALHOST_PORT_PATTERN = re.compile(r"localhost:(\d{2,5})")
_VERSION_SEGMENT_PATTERN = re.compile(r"v\d+", re.IGNORECASE)
_OUT_DIR_PATTERN = re.compile(r"""outDir\s*:\s*["']([^"']+)["']""")

# Ordered by priority: env-derived defaults, runtime entry points, literals.
_SOURCE_PORT_PATTERNS = (
    re.compile(r"process\.env\.PORT\s*\|\|\s*(\d{2,5})"),
    re.compile(r"process\.env\.PORT\s*\?\?\s*(\d{2,5})"),
    re.compile(r"runserver\s+0\.0\.0\.0:(\d{2,5})"),
    re.compile(r"--bind\s+0\.0\.0\.0:(\d{2,5})"),
    re.compile(r"\.listen\(\s*(\d{2,5})"),
    re.compile(r"\b(?:const|let|var)\s+PORT\s*=\s*(\d{2,5})\b"),
    re.compile(r"app\.run\([^)]*?\bport\s*=\s*(\d{2,5})"),
)

_HEALTH_PROBE_MARKERS = ("health", "ping", "ready", "status")

# Fallback probes when the frontend never calls an API path we can parse.
_FALLBACK_API_BASES = ("/api",)
_FALLBACK_PROBE_PATHS = ("/api/health", "/api")


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def normalize_path(path: str) -> str:
    normalized = str(path).replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def basename(path: str) -> str:
    return normalize_path(path).split("/")[-1]


def files_under(files: Mapping[str, str], directory: str) -> dict[str, str]:
    """Return the files located inside ``directory`` (any depth)."""
    prefix = f"{directory}/"
    return {
        key: content
        for key, content in (files or {}).items()
        if normalize_path(key).startswith(prefix)
    }


def _load_json(content: str | None) -> dict:
    try:
        data = json.loads(content or "")
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _first(scoped: Mapping[str, str], name: str) -> str | None:
    for key in scoped:
        if basename(key).lower() == name.lower():
            return key
    return None


def resolve_service_directories(
    files: Mapping[str, str],
    tree: list[dict] | None = None,
) -> tuple[str | None, str | None]:
    """
    Decision-layer gate.

    Delegates to the existing CloudWise structural rule so the adapter is
    selected for exactly the repositories the legacy split branch handles.
    ``tree`` is accepted for signature symmetry but unused by the rule.
    """
    return _resolve_service_directories(files or {})


def find_frontend_directory(files: Mapping[str, str]) -> str | None:
    """Top-level directory holding a frontend application, if any."""
    for key in files:
        parts = normalize_path(key).split("/")
        if (
            len(parts) >= 2
            and parts[0] in FRONTEND_DIRECTORIES
            and parts[-1].lower() == "package.json"
        ):
            return parts[0]
    return None


def find_backend_directory(files: Mapping[str, str]) -> str | None:
    """Top-level directory holding a backend application, if any."""
    for key in files:
        parts = normalize_path(key).split("/")
        if len(parts) < 2 or parts[0] not in BACKEND_DIRECTORIES:
            continue
        basename_lower = parts[-1].lower()
        if (
            basename_lower == "package.json"
            or basename_lower in BACKEND_MARKER_FILENAMES
            or basename_lower.startswith("build.gradle")
        ):
            return parts[0]
    return None


# ---------------------------------------------------------------------------
# Package manager / commands
# ---------------------------------------------------------------------------

def detect_node_package_manager(files: Mapping[str, str], directory: str) -> str:
    names = {basename(key).lower() for key in files_under(files, directory)}
    if "pnpm-lock.yaml" in names:
        return "pnpm"
    if "yarn.lock" in names:
        return "yarn"
    if "bun.lock" in names or "bun.lockb" in names:
        return "bun"
    return "npm"


def _has_lockfile(files: Mapping[str, str], directory: str) -> bool:
    names = {basename(key).lower() for key in files_under(files, directory)}
    return bool(
        names
        & {
            "package-lock.json",
            "pnpm-lock.yaml",
            "yarn.lock",
            "bun.lock",
            "bun.lockb",
        }
    )


def install_command(package_manager: str, *, lockfile: bool) -> str:
    if package_manager == "yarn":
        return "yarn install --frozen-lockfile" if lockfile else "yarn install"
    if package_manager == "pnpm":
        return (
            "pnpm install --frozen-lockfile" if lockfile else "pnpm install"
        )
    if package_manager == "bun":
        return "bun install"
    if lockfile:
        return "npm ci"
    return "npm install"


# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------

def _frontend_build_env(scoped: Mapping[str, str]) -> tuple[str, ...]:
    """Build-time environment variable names the frontend reads."""
    found: list[str] = []

    def _record(name: str) -> None:
        if name.startswith(_FRONTEND_ENV_PREFIXES) and name not in found:
            found.append(name)

    # Names declared in env templates (values are never stored).
    templates = {
        key: content
        for key, content in scoped.items()
        if basename(key).lower() in ENV_TEMPLATE_FILENAMES
    }
    for name in detect_environment_variables(templates):
        _record(name)

    # Names referenced from source code (import.meta.env.VITE_X / process.env.*).
    patterns = tuple(
        re.compile(rf"(?:import\.meta\.env|process\.env)\.({prefix}[A-Z0-9_]*)")
        for prefix in _FRONTEND_ENV_PREFIXES
    )
    for key, content in scoped.items():
        if not content or not str(key).lower().endswith(_CODE_SUFFIXES):
            continue
        for pattern in patterns:
            for match in pattern.finditer(content):
                _record(match.group(1))
    return tuple(found)


def _frontend_output_directory(
    scoped: Mapping[str, str], framework_slug: str | None,
) -> str | None:
    if framework_slug == "nextjs":
        return None  # Next.js keeps build output in .next (SSR runtime)
    if framework_slug == "cra":
        return "build"
    for key, content in scoped.items():
        if basename(key).lower().startswith("vite.config") and content:
            match = _OUT_DIR_PATTERN.search(content)
            if match:
                return match.group(1).rstrip("/")
    return "dist"


def detect_frontend_profile(
    files: Mapping[str, str],
    directory: str,
    *,
    tree: list[dict] | None = None,
) -> FrontendProfile:
    """Profile the frontend application inside ``directory``."""
    scoped = files_under(files, directory)
    pkg_key = _first(scoped, "package.json")
    pkg = _load_json(scoped.get(pkg_key)) if pkg_key else {}
    raw_scripts = pkg.get("scripts")
    scripts = raw_scripts if isinstance(raw_scripts, dict) else {}
    deps = _package_dependencies(files, pkg_key) if pkg_key else {}

    resolved = _resolve_frontend_framework(deps, files) or {}
    framework_slug = _FRONTEND_FRAMEWORK_SLUGS.get(resolved.get("framework") or "")
    technology = resolved.get("technology") or "JavaScript"

    package_manager = detect_node_package_manager(files, directory)
    lockfile = _has_lockfile(files, directory)

    build_command = None
    if scripts.get("build"):
        build_command = f"{package_manager} run build"

    start_command = f"{package_manager} start" if scripts.get("start") else None
    port = 3000 if framework_slug == "nextjs" else 80

    return FrontendProfile(
        path=directory,
        runtime="node",
        technology=technology,
        framework=framework_slug or "",
        package_manager=package_manager,
        manifest_path=pkg_key,
        install_command=install_command(package_manager, lockfile=lockfile),
        build_command=build_command,
        output_directory=_frontend_output_directory(scoped, framework_slug),
        start_command=start_command,
        port=port,
        build_time_env=_frontend_build_env(scoped),
    )


# ---------------------------------------------------------------------------
# Backend port (priority: Dockerfile → env → source → docs → default)
# ---------------------------------------------------------------------------

def _port_from_dockerfiles(files: Mapping[str, str], directory: str) -> int | None:
    for key, content in files_under(files, directory).items():
        if basename(key).lower() not in DOCKERFILE_BASENAMES:
            continue
        match = _EXPOSE_PATTERN.search(content or "")
        if match:
            return int(match.group(1))
    return None


def _port_from_env_templates(files: Mapping[str, str], directory: str) -> int | None:
    # Prefer templates inside the backend directory, then the repository root.
    scoped_keys = [
        key
        for key in files_under(files, directory)
        if basename(key).lower() in ENV_TEMPLATE_FILENAMES
        or basename(key).lower().startswith("docker-compose")
    ]
    root_keys = [
        key
        for key in files
        if "/" not in normalize_path(key)
        and (
            basename(key).lower() in ENV_TEMPLATE_FILENAMES
            or basename(key).lower().startswith("docker-compose")
        )
    ]
    for key in scoped_keys + root_keys:
        match = _ENV_PORT_PATTERN.search(files[key] or "")
        if match:
            return int(match.group(1))
    return None


def _port_from_source(files: Mapping[str, str], directory: str) -> int | None:
    scoped = [
        (key, content)
        for key, content in files_under(files, directory).items()
        if str(key).lower().endswith(_CODE_SUFFIXES)
    ]
    for pattern in _SOURCE_PORT_PATTERNS:
        for _, content in scoped:
            match = pattern.search(content or "")
            if match:
                return int(match.group(1))
    return None


def _port_from_docs(files: Mapping[str, str]) -> int | None:
    for key in sorted(files, key=normalize_path):
        if not basename(key).lower().startswith("readme"):
            continue
        match = _LOCALHOST_PORT_PATTERN.search(files[key] or "")
        if match:
            return int(match.group(1))
    return None


def detect_backend_port(
    files: Mapping[str, str],
    directory: str,
    *,
    technology: str | None = None,
    framework: str | None = None,
) -> tuple[int | None, str]:
    """
    Resolve the backend port and record which evidence was used.

    Returns ``(port, evidence)`` where evidence is one of
    ``dockerfile`` | ``env`` | ``source`` | ``readme`` | ``default`` | ``none``.
    """
    port = _port_from_dockerfiles(files, directory)
    if port:
        return port, "dockerfile"

    port = _port_from_env_templates(files, directory)
    if port:
        return port, "env"

    port = _port_from_source(files, directory)
    if port:
        return port, "source"

    port = _port_from_docs(files)
    if port:
        return port, "readme"

    default = _backend_default_port({"technology": technology, "framework": framework})
    if default:
        return default, "default"
    return None, "none"


# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------

def _backend_runtime(
    scoped: Mapping[str, str], technology_label: str | None,
) -> tuple[str, str | None, str | None]:
    """Return ``(runtime, technology, framework)`` for the backend directory."""
    names = {basename(key).lower() for key in scoped}
    if "package.json" in names:
        return "node", "Node.js", None
    if "requirements.txt" in names or "pyproject.toml" in names:
        return "python", "Python", None
    if "pom.xml" in names or "build.gradle" in names or "build.gradle.kts" in names:
        return "java", "Java", None
    if technology_label == "Node.js":
        return "node", "Node.js", None
    if technology_label == "Python":
        return "python", "Python", None
    if technology_label == "Java":
        return "java", "Java", None
    return "unknown", technology_label, None


def _relative(scoped_key: str | None, directory: str) -> str | None:
    """Path relative to the service directory (build-context relative)."""
    if not scoped_key:
        return None
    normalized = normalize_path(scoped_key)
    prefix = f"{directory}/"
    if normalized.startswith(prefix):
        return normalized[len(prefix):]
    return normalized


def _node_start(
    scoped: Mapping[str, str], directory: str, package_manager: str,
) -> tuple[str | None, str | None, str | None, str | None]:
    """Return ``(start_script, entry_file, start_command, issue)``."""
    pkg_key = _first(scoped, "package.json")
    pkg = _load_json(scoped.get(pkg_key)) if pkg_key else {}
    raw_scripts = pkg.get("scripts")
    scripts = raw_scripts if isinstance(raw_scripts, dict) else {}
    raw_start = scripts.get("start")
    start_script = raw_start if isinstance(raw_start, str) else None

    # Prefer a top-level entry file, then a nested one, then package.json main.
    entry_key = None
    for name in NODE_ENTRY_FILES:
        top_level = next(
            (
                key for key in scoped
                if normalize_path(key).count("/") == 1 and basename(key) == name
            ),
            None,
        )
        if top_level:
            entry_key = top_level
            break
    if entry_key is None:
        entry_key = next(
            (key for key in scoped if basename(key) in NODE_ENTRY_FILES), None,
        )
    if entry_key is None and isinstance(pkg.get("main"), str):
        entry_key = pkg["main"]

    entry_file = _relative(entry_key, directory)

    if start_script:
        # The npm script itself runs inside the container workdir.
        return start_script, entry_file, f"{package_manager} start", None
    if entry_file:
        return None, entry_file, f"node {entry_file}", None
    return (
        None,
        None,
        None,
        "Backend directory detected but backend package.json has no start script",
    )


def _python_corpus(scoped: Mapping[str, str]) -> str:
    parts = []
    for key, content in scoped.items():
        if basename(key).lower() in ("requirements.txt", "pyproject.toml", "pipfile"):
            parts.append((content or "").lower())
    return "\n".join(parts)


def _python_start(
    scoped: Mapping[str, str], directory: str, port: int | None,
) -> tuple[str | None, str | None, str | None, str | None]:
    """Return ``(start_script, entry_file, start_command, issue)``."""
    target = f"0.0.0.0:{port}" if port else "0.0.0.0:8000"

    manage_key = _first(scoped, "manage.py")
    if manage_key:
        return None, _relative(manage_key, directory), f"python manage.py runserver {target}", None

    corpus = _python_corpus(scoped)
    entry_key = None
    for name in PYTHON_ENTRY_FILES:
        found = _first(scoped, name)
        if found:
            entry_key = found
            break
    entry = _relative(entry_key, directory)

    if "flask" in corpus:
        module = entry.rsplit("/", 1)[-1].rsplit(".", 1)[0] if entry else "app"
        return None, entry, f"gunicorn --bind {target} {module}:app", None
    if entry:
        return None, entry, f"python {entry}", None
    return (
        None,
        None,
        None,
        "Backend directory detected but no Python entry point was found",
    )


def detect_backend_profile(
    files: Mapping[str, str],
    directory: str,
    *,
    backend_info: Mapping | None = None,
) -> tuple[BackendProfile, list[str]]:
    """Profile the backend application inside ``directory``."""
    issues: list[str] = []
    scoped = files_under(files, directory)
    backend_info = dict(backend_info or {})

    runtime, technology, framework = _backend_runtime(
        scoped, backend_info.get("technology"),
    )
    # Framework detail (Express / Django / Flask / Spring Boot ...) comes from
    # the existing CloudWise analysis so labels stay consistent.
    framework = backend_info.get("framework") or framework

    if runtime == "node":
        package_manager = detect_node_package_manager(files, directory)
        lockfile = _has_lockfile(files, directory)
        install = install_command(package_manager, lockfile=lockfile)
        manifest = _first(scoped, "package.json")
    elif runtime == "python":
        package_manager = "pip"
        install = "pip install -r requirements.txt"
        manifest = _first(scoped, "requirements.txt") or _first(scoped, "pyproject.toml")
    elif runtime == "java":
        package_manager = "maven" if _first(scoped, "pom.xml") else "gradle"
        install = None
        manifest = _first(scoped, "pom.xml") or _first(scoped, "build.gradle") or _first(
            scoped, "build.gradle.kts",
        )
    else:
        package_manager = ""
        install = None
        manifest = None

    port, port_evidence = detect_backend_port(
        files, directory, technology=technology, framework=framework,
    )

    start_script = None
    entry_file = None
    start_command = None

    if runtime == "node":
        start_script, entry_file, start_command, issue = _node_start(
            scoped, directory, package_manager,
        )
        if issue:
            issues.append(issue)
    elif runtime == "python":
        start_script, entry_file, start_command, issue = _python_start(
            scoped, directory, port,
        )
        if issue:
            issues.append(issue)
    elif runtime == "java":
        entry_file = None
        start_command = "java -jar app.jar"

    if port is None:
        issues.append(f"Backend port could not be detected for '{directory}'")

    profile = BackendProfile(
        path=directory,
        runtime=runtime,
        technology=technology or "",
        framework=framework or "",
        package_manager=package_manager,
        manifest_path=manifest,
        install_command=install,
        start_script=start_script,
        entry_file=entry_file,
        start_command=start_command,
        port=port,
        port_evidence=port_evidence,
    )
    return profile, issues


# ---------------------------------------------------------------------------
# Frontend → backend API paths
# ---------------------------------------------------------------------------

def detect_api_paths(
    files: Mapping[str, str],
    frontend_directory: str,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """
    Discover API paths the frontend calls.

    Returns ``(base_paths, probe_paths)``. SPA router paths (``/doctors``,
    ``/booking`` ...) are collected first and excluded so only real API
    endpoints remain. When nothing is found the ``/api`` defaults are used.
    """
    scoped = files_under(files, frontend_directory)
    code = [
        (key, content)
        for key, content in scoped.items()
        if str(key).lower().endswith(_CODE_SUFFIXES) and content
    ]

    spa_routes: set[str] = set()
    for _, content in code:
        for match in _SPA_ROUTE_PATTERN.finditer(content):
            route = match.group(1).rstrip("/") or "/"
            spa_routes.add(route)

    candidates: list[str] = []
    for _, content in code:
        for match in _API_PATH_PATTERN.finditer(content):
            raw = match.group(1)
            scheme_at = raw.find("://")
            if scheme_at != -1:
                # Absolute URL (http://localhost:5000/api/...) — keep the path
                # so the same-origin nginx routing still applies.
                path_at = raw.find("/", scheme_at + 3)
                raw = raw[path_at:] if path_at != -1 else ""
            path = "/" + raw.lstrip("/")
            path = path.rstrip("/")
            if not path or path in spa_routes:
                continue
            if path not in candidates:
                candidates.append(path)

    base_paths: list[str] = []
    for path in candidates:
        segments = path.lstrip("/").split("/")
        base = f"/{segments[0]}"
        if len(segments) > 1 and _VERSION_SEGMENT_PATTERN.fullmatch(segments[1]):
            base = f"{base}/{segments[1]}"
        if base not in base_paths:
            base_paths.append(base)

    preferred = [
        path for path in candidates
        if any(marker in path.lower() for marker in _HEALTH_PROBE_MARKERS)
    ]
    remaining = [path for path in candidates if path not in preferred]
    probe_paths = (preferred + remaining)[:4]

    return (
        tuple(base_paths) if base_paths else _FALLBACK_API_BASES,
        tuple(probe_paths) if probe_paths else _FALLBACK_PROBE_PATHS,
    )
