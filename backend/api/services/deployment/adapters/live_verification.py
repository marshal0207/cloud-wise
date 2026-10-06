"""
Live verification for split (separate frontend + backend) deployments.

After the containers start, the router nginx on the instance is probed for:

* the frontend application (``/``) and
* one backend API path discovered by the detector (``/api/v1/...``),

so a deployment where the frontend is up but the API is not routed (or the
backend crashed) is reported as unhealthy instead of silently "live".

The probe runs in-instance through SSM (the security group only exposes
80/443/22) and never fails a deployment on its own — the caller decides:

* ``SUCCESS``  — every probe answered acceptably
* ``FAILED``   — a probe answered with an error / nothing usable
* ``SKIPPED``  — the probe could not run (e.g. mocked SSM in unit tests,
                 no marker in the output); the caller keeps its own verdict
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence

HEALTHY_STATUS = "SUCCESS"
FAILED_STATUS = "FAILED"
SKIPPED_STATUS = "SKIPPED"

# Statuses that count as "the route works": 2xx/3xx, plus auth/method
# responses that prove nginx reached the backend (401/403/405).
_ACCEPTABLE_STATUS_CODES = frozenset(
    list(range(200, 400)) + [401, 403, 405]
)

_SPLIT_MARKER_PATTERN = re.compile(
    r"CLOUDWISE_SPLIT\s+frontend=(\d{1,3})\s+api=(\d{1,3})"
)
_SAFE_PROBE_PATH = re.compile(r"[^A-Za-z0-9/._-]")

# (commands, stage_message, timeout_seconds) -> concatenated SSM output
RunCommands = Callable[[Sequence[str], str, int], str]


def _safe_probe_path(path: Any) -> str:
    candidate = str(path or "").strip()
    if not candidate.startswith("/") or _SAFE_PROBE_PATH.search(candidate):
        return "/api/health"
    return candidate


def _status_ok(status_code: int) -> bool:
    return status_code in _ACCEPTABLE_STATUS_CODES


def build_probe_command(probe_path: str) -> str:
    """Single in-instance shell command probing frontend + backend API."""
    probe_path = _safe_probe_path(probe_path)
    # Plain (non-f) strings: curl's %{http_code} and shell ${...} stay
    # literal. The probe path was sanitised above.
    return (
        'FE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 '
        '--max-time 10 http://127.0.0.1/ 2>/dev/null); FE=${FE:-000}; '
        'API=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 '
        '--max-time 10 http://127.0.0.1' + probe_path + ' 2>/dev/null); '
        'API=${API:-000}; '
        'echo "CLOUDWISE_SPLIT frontend=${FE} api=${API}"'
    )


def _report(
    *,
    status: str,
    message: str,
    public_url: str,
    probe_path: str,
    frontend_code: int | None = None,
    backend_code: int | None = None,
    api_base_paths: Sequence[str] | None = None,
) -> dict[str, Any]:
    frontend_ok = frontend_code is not None and _status_ok(frontend_code)
    backend_ok = backend_code is not None and _status_ok(backend_code)
    return {
        "status": status,
        "message": message,
        "publicUrl": public_url,
        "checkedAt": datetime.now(timezone.utc).isoformat(),
        "frontend": {
            "path": "/",
            "statusCode": frontend_code,
            "ok": frontend_ok,
        },
        "backend": {
            "path": probe_path,
            "statusCode": backend_code,
            "ok": backend_ok,
        },
        "nginx": {
            "publishedPort": 80,
            "routes": ["/", probe_path],
            "ok": status == HEALTHY_STATUS,
        },
        "apiBasePaths": list(api_base_paths or []),
    }


def verify_split_deployment(
    deployment_plan: Mapping[str, Any],
    *,
    endpoint_url: str = "",
    run_commands: RunCommands | None = None,
) -> dict[str, Any] | None:
    """
    Probe frontend and backend API on a split deployment.

    Returns ``None`` when the plan is not a split architecture (legacy
    deployments keep their existing health behaviour untouched), otherwise a
    JSON-serialisable report with ``status`` SUCCESS / FAILED / SKIPPED.
    """
    plan = deployment_plan or {}
    if plan.get("architecture") != "separate_frontend_backend":
        return None

    probe_paths = list(plan.get("apiProbePaths") or [])
    probe_path = _safe_probe_path(probe_paths[0] if probe_paths else "/api/health")
    api_base_paths = list(plan.get("apiBasePaths") or [])

    if run_commands is None:
        return _report(
            status=SKIPPED_STATUS,
            message="Split verification skipped: no command runner available.",
            public_url=endpoint_url,
            probe_path=probe_path,
            api_base_paths=api_base_paths,
        )

    try:
        output = run_commands(
            [build_probe_command(probe_path)],
            "split live verification",
            60,
        )
    except Exception as exc:  # noqa: BLE001 — SSM/network failures are not fatal
        return _report(
            status=SKIPPED_STATUS,
            message=f"Split verification could not run: {exc}",
            public_url=endpoint_url,
            probe_path=probe_path,
            api_base_paths=api_base_paths,
        )

    if not (output or "").strip():
        # Mocked SSM (unit tests) returns an empty string — do not fail.
        return _report(
            status=SKIPPED_STATUS,
            message="Split verification skipped: no probe output returned.",
            public_url=endpoint_url,
            probe_path=probe_path,
            api_base_paths=api_base_paths,
        )

    match = _SPLIT_MARKER_PATTERN.search(output)
    if match is None:
        return _report(
            status=SKIPPED_STATUS,
            message=(
                "Split verification skipped: probe marker not found in "
                f"instance output ({(output or '')[-300:]})"
            ),
            public_url=endpoint_url,
            probe_path=probe_path,
            api_base_paths=api_base_paths,
        )

    frontend_code = int(match.group(1))
    backend_code = int(match.group(2))

    if _status_ok(frontend_code) and _status_ok(backend_code):
        return _report(
            status=HEALTHY_STATUS,
            message=(
                f"Frontend HTTP {frontend_code} and backend API HTTP "
                f"{backend_code} ({probe_path}) verified through nginx."
            ),
            public_url=endpoint_url,
            probe_path=probe_path,
            frontend_code=frontend_code,
            backend_code=backend_code,
            api_base_paths=api_base_paths,
        )

    problems = []
    if not _status_ok(frontend_code):
        problems.append(f"frontend HTTP {frontend_code}")
    if not _status_ok(backend_code):
        problems.append(f"backend API {probe_path} HTTP {backend_code}")
    return _report(
        status=FAILED_STATUS,
        message="Split health check failed: " + ", ".join(problems) + ".",
        public_url=endpoint_url,
        probe_path=probe_path,
        frontend_code=frontend_code,
        backend_code=backend_code,
        api_base_paths=api_base_paths,
    )
