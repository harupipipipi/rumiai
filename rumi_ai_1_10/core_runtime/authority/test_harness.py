"""Explicit QA harness for Authority approval settlement.

The harness intentionally drives the normal AuthorityService approval/deny paths
instead of granting permissions directly. It is gated by test-only environment
markers so production code cannot accidentally enable it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from .ui_operator import sign_ui_operator


_TRUE_VALUES = {"1", "true", "yes", "on"}
_PRODUCTION_VALUES = {"prod", "production", "release", "packaged"}


class AuthorityQAModeError(RuntimeError):
    pass


@dataclass(frozen=True)
class AuthorityQAScenario:
    auto_approve_permissions: frozenset[str] = field(default_factory=frozenset)
    auto_deny_permissions: frozenset[str] = field(default_factory=frozenset)
    approval_scope: str = "once"
    deny_reason: str = "denied by authority qa harness"


class AuthorityQAHarness:
    """Test-only settlement helper for LLM/agent QA."""

    def __init__(self, service: Any, *, scenario: AuthorityQAScenario | None = None) -> None:
        assert_authority_test_mode_enabled()
        self._service = service
        self._scenario = scenario or AuthorityQAScenario()
        self._audit("authority_qa_harness_created", {"authority_mode": "test"})

    def approve_once(
        self,
        request_id: str,
        *,
        related_permissions: list[str] | tuple[str, ...] | None = None,
        expires_in_seconds: int | None = None,
    ) -> dict[str, Any]:
        self._audit("authority_qa_approve_once", {"request_id": request_id})
        return self._service.approve_request(
            request_id,
            scope="once",
            related_permissions=related_permissions,
            expires_in_seconds=expires_in_seconds,
            ui_operator=sign_ui_operator(request_id, nonce=f"qa-{request_id}"),
        )

    def approve_persistent(
        self,
        request_id: str,
        *,
        scope: str = "conversation",
        config: dict[str, Any] | None = None,
        related_permissions: list[str] | tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        self._audit("authority_qa_approve_persistent", {"request_id": request_id, "scope": scope})
        return self._service.approve_request(
            request_id,
            scope=scope,
            config=dict(config or {}),
            related_permissions=related_permissions,
            ui_operator=sign_ui_operator(request_id, nonce=f"qa-{request_id}"),
        )

    def deny(self, request_id: str, *, reason: str = "", persist: bool = False) -> dict[str, Any]:
        self._audit("authority_qa_deny", {"request_id": request_id, "persist": bool(persist)})
        return self._service.deny_request(
            request_id,
            reason=reason or self._scenario.deny_reason,
            persist=persist,
            ui_operator=sign_ui_operator(request_id, nonce=f"qa-{request_id}"),
        )

    def expire(self, request_id: str) -> dict[str, Any]:
        store = getattr(self._service, "_request_store", None)
        if store is None or not callable(getattr(store, "set_request_status", None)):
            return {"success": False, "error": "Authority request store unavailable", "status_code": 500}
        request = store.set_request_status(request_id, "expired")
        self._audit("authority_qa_expire", {"request_id": request_id})
        return {"success": request is not None, "request_id": request_id, "expired": request is not None}

    def settle_pending(self) -> list[dict[str, Any]]:
        store = getattr(self._service, "_request_store", None)
        if store is None or not callable(getattr(store, "list_requests", None)):
            return []
        results: list[dict[str, Any]] = []
        for request in store.list_requests("pending"):
            if request.permission_id in self._scenario.auto_deny_permissions:
                results.append(self.deny(request.request_id))
            elif request.permission_id in self._scenario.auto_approve_permissions:
                if self._scenario.approval_scope == "once":
                    results.append(self.approve_once(request.request_id))
                else:
                    results.append(
                        self.approve_persistent(request.request_id, scope=self._scenario.approval_scope)
                    )
        return results

    def _audit(self, action: str, details: dict[str, Any]) -> None:
        store = getattr(self._service, "_request_store", None)
        audit = getattr(store, "audit", None)
        if callable(audit):
            audit(action, {"authority_mode": "test", **dict(details or {})})


def assert_authority_test_mode_enabled(env: dict[str, str] | None = None) -> None:
    env = dict(os.environ if env is None else env)
    if not _truthy(env.get("RUMI_AUTHORITY_TEST_MODE")):
        raise AuthorityQAModeError("RUMI_AUTHORITY_TEST_MODE=1 is required for Authority QA harness")
    if _truthy(env.get("RUMI_PACKAGED_BUILD")) or _truthy(env.get("RUMI_PRODUCTION_BUILD")):
        raise AuthorityQAModeError("Authority QA harness is blocked in packaged production builds")
    profile_values = {
        str(env.get("RUMI_ENV") or "").strip().lower(),
        str(env.get("RUMI_APP_ENV") or "").strip().lower(),
        str(env.get("RUMI_RUNTIME_PROFILE") or "").strip().lower(),
        str(env.get("RUMI_AUTHORITY_PROFILE") or "").strip().lower(),
    }
    if profile_values & _PRODUCTION_VALUES:
        raise AuthorityQAModeError("Authority QA harness is blocked in production profiles")


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in _TRUE_VALUES
