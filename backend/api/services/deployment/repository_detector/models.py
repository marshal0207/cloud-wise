"""
Structured profiles produced by the CloudWise repository detector.

This module belongs to the *additive* deployment adaptation layer. It only
describes what the detector found in a repository — it never mutates the
existing deployment pipeline, models, or APIs.

Architecture values
-------------------
``separate_frontend_backend`` — repository contains a frontend application
    directory and a different backend application directory (for example
    ``frontend/`` + ``backend/``). Only these repositories are routed to
    the new deployment adapter.
``frontend_only`` / ``backend_only`` / ``unknown`` — everything else keeps
    the existing CloudWise deployment behaviour untouched.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

ARCHITECTURE_SEPARATE = "separate_frontend_backend"
ARCHITECTURE_FRONTEND_ONLY = "frontend_only"
ARCHITECTURE_BACKEND_ONLY = "backend_only"
ARCHITECTURE_UNKNOWN = "unknown"


@dataclass(frozen=True)
class FrontendProfile:
    """What the detector learned about the frontend application."""

    path: str
    runtime: str = "node"
    technology: str = ""
    framework: str = ""
    package_manager: str = "npm"
    manifest_path: str | None = None
    install_command: str | None = None
    build_command: str | None = None
    output_directory: str | None = None
    start_command: str | None = None
    port: int = 80
    build_time_env: tuple[str, ...] = field(default_factory=tuple)

    @property
    def root(self) -> str:
        """Build context path relative to the repository root ('.' at root)."""
        return self.path or "."

    def to_manifest(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "root": self.root,
            "runtime": self.runtime,
            "technology": self.technology,
            "framework": self.framework,
            "packageManager": self.package_manager,
            "manifest": self.manifest_path,
            "installCommand": self.install_command,
            "buildCommand": self.build_command,
            "outputDirectory": self.output_directory,
            "startCommand": self.start_command,
            "port": self.port,
            "buildTimeEnv": list(self.build_time_env),
        }


@dataclass(frozen=True)
class BackendProfile:
    """What the detector learned about the backend application."""

    path: str
    runtime: str = "unknown"
    technology: str = ""
    framework: str = ""
    package_manager: str = ""
    manifest_path: str | None = None
    install_command: str | None = None
    start_script: str | None = None
    entry_file: str | None = None
    start_command: str | None = None
    port: int | None = None
    port_evidence: str = "none"

    @property
    def root(self) -> str:
        return self.path or "."

    @property
    def port_detected(self) -> bool:
        return isinstance(self.port, int) and self.port > 0

    def to_manifest(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "root": self.root,
            "runtime": self.runtime,
            "technology": self.technology,
            "framework": self.framework,
            "packageManager": self.package_manager,
            "manifest": self.manifest_path,
            "installCommand": self.install_command,
            "startScript": self.start_script,
            "entryFile": self.entry_file,
            "startCommand": self.start_command,
            "port": self.port,
            "portEvidence": self.port_evidence,
        }


@dataclass(frozen=True)
class RepositoryProfile:
    """Top-level result of repository structure detection."""

    architecture: str
    frontend: FrontendProfile | None = None
    backend: BackendProfile | None = None
    database_type: str | None = None
    api_base_paths: tuple[str, ...] = field(default_factory=tuple)
    api_probe_paths: tuple[str, ...] = field(default_factory=tuple)
    required_env_vars: tuple[str, ...] = field(default_factory=tuple)
    issues: tuple[str, ...] = field(default_factory=tuple)
    application_type: str = ""

    @property
    def requires_separate_frontend_backend(self) -> bool:
        """Decision-layer gate: use the new adapter only for split repos."""
        return self.architecture == ARCHITECTURE_SEPARATE

    @property
    def supports_split_deployment(self) -> bool:
        """Split architecture with both applications analysable."""
        if not self.requires_separate_frontend_backend:
            return False
        return self.frontend is not None and self.backend is not None

    def to_manifest(self) -> dict[str, Any]:
        """Internal deployment manifest (Phase 3) consumed by the adapter."""
        manifest: dict[str, Any] = {
            "architecture": self.architecture,
            "frontend": self.frontend.to_manifest() if self.frontend else None,
            "backend": self.backend.to_manifest() if self.backend else None,
            "database": {"type": (self.database_type or "").lower() or None},
            "api": {
                "basePaths": list(self.api_base_paths),
                "probePaths": list(self.api_probe_paths),
            },
            "requiredEnvVars": list(self.required_env_vars),
            "issues": list(self.issues),
        }
        return manifest

    def summary(self) -> str:
        """One-line description used in deployment logs."""
        if not self.requires_separate_frontend_backend:
            return f"architecture={self.architecture}"
        frontend_path = self.frontend.path if self.frontend else "?"
        backend_path = self.backend.path if self.backend else "?"
        backend_port = self.backend.port if self.backend else None
        return (
            f"architecture={self.architecture} "
            f"frontend={frontend_path} backend={backend_path} "
            f"backendPort={backend_port}"
        )
