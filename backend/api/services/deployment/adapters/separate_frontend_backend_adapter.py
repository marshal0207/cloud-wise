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
    spa_conf = (
        r"server {\n"
        r"    listen 80;\n"
        r"    server_name _;\n"
        r"    root /usr/share/nginx/html;\n"
        r"    index index.html;\n"
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

    # ---- deployment plan ----
    deployment_plan = build_deployment_plan(
        generated_files=generated,
        analysis=analysis,
        containers=["frontend", "backend", "nginx"],
        ports=[PUBLISHED_PORT],
        requires_nginx=True,
    )
    deployment_plan.update({
        "architecture": profile.architecture,
        "manifest": profile.to_manifest(),
        "frontendPort": frontend_port,
        "backendPort": backend_port,
        "portEvidence": backend.port_evidence,
        "apiBasePaths": list(profile.api_base_paths),
        "apiProbePaths": list(profile.api_probe_paths),
        "issues": list(profile.issues),
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
