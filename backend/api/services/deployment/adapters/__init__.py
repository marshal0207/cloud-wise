"""
Additive deployment adaptation layer.

Re-exports the split-architecture entry points:

* :func:`generate_split_deployment` — renders the deployment files for
  repositories with a separate ``frontend/`` + ``backend/`` layout
* :func:`readiness_problem` — pre-flight gate used by the deploy views
* :func:`verify_split_deployment` — in-instance live verification reported
  through the ``health`` key of the deploy result

Nothing in this package changes the legacy (single-service / legacy
split) deployment path; it is only entered when the repository detector
classifies a repository as ``separate_frontend_backend``.
"""

from .live_verification import verify_split_deployment
from .separate_frontend_backend_adapter import (
    generate_split_deployment,
    readiness_problem,
)

__all__ = [
    "generate_split_deployment",
    "readiness_problem",
    "verify_split_deployment",
]
