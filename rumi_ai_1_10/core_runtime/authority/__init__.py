"""Authority service public entry points."""

from __future__ import annotations

from .models import AuthorityDecision, AuthorityRequest, AuthorityResource
from .principal import build_principal_id
from .service import AuthorityService
from .test_harness import AuthorityQAHarness, AuthorityQAModeError, AuthorityQAScenario


def get_authority_service() -> AuthorityService:
    from core_runtime.di_container import get_container

    return get_container().get("authority_service")


__all__ = [
    "AuthorityDecision",
    "AuthorityRequest",
    "AuthorityResource",
    "AuthorityQAHarness",
    "AuthorityQAModeError",
    "AuthorityQAScenario",
    "AuthorityService",
    "build_principal_id",
    "get_authority_service",
]
