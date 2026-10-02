"""
Repository structure detection for the additive deployment adaptation layer.

``detect_repository`` returns a :class:`RepositoryProfile` describing whether
the repository is a split ``frontend/`` + ``backend/`` layout and what each
service needs to be built and run in containers.

Only repositories whose structure matches the *existing* CloudWise split
rule are classified as ``separate_frontend_backend``; every other repository
is classified as frontend-only / backend-only / unknown and continues to use
the untouched legacy deployment path.
"""

from __future__ import annotations

from typing import Mapping

from ...tech_stack_detector import analyze_repository
from .models import (
    ARCHITECTURE_BACKEND_ONLY,
    ARCHITECTURE_FRONTEND_ONLY,
    ARCHITECTURE_SEPARATE,
    ARCHITECTURE_UNKNOWN,
    RepositoryProfile,
)
from .rules import (
    detect_api_paths,
    detect_backend_profile,
    detect_frontend_profile,
    find_backend_directory,
    find_frontend_directory,
    resolve_service_directories,
)

_NON_SPLIT_ARCHITECTURES = {
    "frontend-only": ARCHITECTURE_FRONTEND_ONLY,
    "backend-only": ARCHITECTURE_BACKEND_ONLY,
}


def detect_repository(
    files: Mapping[str, str],
    *,
    tree: list[dict] | None = None,
    repository_size: dict | None = None,
) -> RepositoryProfile:
    """
    Analyse repository structure and build the deployment profile.

    Reuses the existing CloudWise analysis (framework / database / env
    labels) so user-facing detection output stays identical, and adds the
    structural facts the split-architecture adapter needs.
    """
    files = dict(files or {})
    tree = list(tree or [])

    analysis = analyze_repository(files, tree=tree, repository_size=repository_size)
    backend_info = analysis.get("backend") or {}
    application_type = analysis.get("applicationType") or ""
    database = analysis.get("database") or {}
    env_vars = analysis.get("environmentVariables") or []

    # Decision gate: exactly the repositories the legacy split branch uses.
    frontend_dir, backend_dir = resolve_service_directories(files, tree=tree)
    split_architecture = bool(frontend_dir and backend_dir)
    if not split_architecture:
        # Still profile whichever service directories exist (informational);
        # the architecture below decides whether the adapter is used.
        frontend_dir = find_frontend_directory(files)
        backend_dir = find_backend_directory(files)

    issues: list[str] = []
    frontend = None
    backend = None
    if frontend_dir:
        frontend = detect_frontend_profile(files, frontend_dir, tree=tree)
        if not frontend.build_command:
            issues.append(
                f"Frontend directory '{frontend_dir}' package.json has no "
                f"build script"
            )
    if backend_dir:
        backend, backend_issues = detect_backend_profile(
            files, backend_dir, backend_info=backend_info,
        )
        issues.extend(backend_issues)

    if split_architecture and frontend_dir is not None:
        architecture = ARCHITECTURE_SEPARATE
        base_paths, probe_paths = detect_api_paths(files, frontend_dir)
    else:
        architecture = _NON_SPLIT_ARCHITECTURES.get(
            application_type, ARCHITECTURE_UNKNOWN,
        )
        base_paths, probe_paths = (), ()

    return RepositoryProfile(
        architecture=architecture,
        frontend=frontend,
        backend=backend,
        database_type=database.get("type"),
        api_base_paths=base_paths,
        api_probe_paths=probe_paths,
        required_env_vars=tuple(env_vars),
        issues=tuple(issues),
        application_type=application_type,
    )
