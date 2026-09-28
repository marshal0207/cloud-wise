"""
CloudWise repository detector (additive deployment adaptation layer).

Entry point::

    from api.services.deployment.repository_detector import detect_repository
    profile = detect_repository(files, tree=tree)

``profile.requires_separate_frontend_backend`` is the decision-layer gate
that routes a deployment to the split frontend/backend adapter.
"""

from .detector import detect_repository
from .models import (
    ARCHITECTURE_BACKEND_ONLY,
    ARCHITECTURE_FRONTEND_ONLY,
    ARCHITECTURE_SEPARATE,
    ARCHITECTURE_UNKNOWN,
    BackendProfile,
    FrontendProfile,
    RepositoryProfile,
)

__all__ = [
    "detect_repository",
    "RepositoryProfile",
    "FrontendProfile",
    "BackendProfile",
    "ARCHITECTURE_SEPARATE",
    "ARCHITECTURE_FRONTEND_ONLY",
    "ARCHITECTURE_BACKEND_ONLY",
    "ARCHITECTURE_UNKNOWN",
]
