"""Opt-in Authority QA settlement harness.

This module deliberately drives the normal Authority service approval and deny
methods instead of replacing them. The only direct store operation here is the
synthetic timeout case, which has no production settlement equivalent.
"""

from __future__ import annotations

import hmac
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import AuthorityRequest
from .request_store import sanitize_authority_resource
from .ui_operator import sign_ui_operator


TEST_MODE_ENV = "RUMI_AUTHORITY_TEST_MODE"
TEST_POLICY_ENV = "RUMI_AUTHORITY_TEST_POLICY"
TEST_TOKEN_ENV = "RUMI_AUTHORITY_TEST_TOKEN"

_TRUTHY = {"1", "true", "yes", "on"}
_PRODUCTION_VALUES = {"prod", "production", "release", "stable"}
_DEV_PROFILE_VALUES = {"dev", "development", "test", "testing", "ci", "local"}
_PRODUCTION_VALUE_KEYS = (
    "RUMI_ENVIRONMENT",
    "RUMI_APP_ENV",
    "RUMI_RUNTIME_ENV",
    "RUMI_BUILD_CHANNEL",
    "RUMI_RELEASE_CHANNEL",
)
_PRODUCTION_BOOL_KEYS = (
    "RUMI_PACKAGED",
    "RUMI_PRODUCTION",
    "RUMI_IS_PACKAGED",
    "TAURI_ENV_PRODUCTION",
)
_DEV_PROFILE_KEYS = (
    "RUMI_ENVIRONMENT",
    "RUMI_APP_ENV",
    "RUMI_RUNTIME_ENV",
    "RUMI_TEST_PROFILE",
)

_APPROVE = {"approve", "auto_approve", "allow", "approved"}
_DENY = {"deny", "auto_deny", "denied"}
_TIMEOUT = {"timeout", "synthetic_timeout", "expire", "expired"}
_CANCEL = {"cancel", "synthetic_cancel", "cancelled", "canceled"}
_REQUIRE_SYNTHETIC = {"require_synthetic", "manual", "pending"}


@dataclass(frozen=True)
class AuthorityTestModeStatus:
    enabled: bool
    reason: str
    status_code: int = 200
    markers: tuple[str, ...] = ()

    def to_error(self) -> dict[str, Any]:
        return {
            "success": False,
            "error": self.reason,
            "status_code": self.status_code,
            "authority_mode": "test",
            "markers": list(self.markers),
        }


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in _TRUTHY


def _normalized_env(env: dict[str, str] | None = None) -> dict[str, str]:
    source = os.environ if env is None else env
    return {str(key): str(value or "").strip() for key, value in source.items()}


def _production_markers(env: dict[str, str]) -> tuple[str, ...]:
    markers: list[str] = []
    for key in _PRODUCTION_VALUE_KEYS:
        value = str(env.get(key) or "").strip().lower()
        if value in _PRODUCTION_VALUES:
            markers.append(f"{key}={value}")
    for key in _PRODUCTION_BOOL_KEYS:
        if _truthy(env.get(key)):
            markers.append(f"{key}=true")
    return tuple(markers)


def _dev_profile_active(env: dict[str, str]) -> bool:
    for key in _DEV_PROFILE_KEYS:
        if str(env.get(key) or "").strip().lower() in _DEV_PROFILE_VALUES:
            return True
    return False


def authority_test_mode_status(env: dict[str, str] | None = None) -> AuthorityTestModeStatus:
    current = _normalized_env(env)
    if not _truthy(current.get(TEST_MODE_ENV)):
        return AuthorityTestModeStatus(False, "Authority test mode is disabled", 404)
    markers = _production_markers(current)
    if markers and not _dev_profile_active(current):
        return AuthorityTestModeStatus(
            False,
            "Authority test mode cannot run under a production or packaged runtime profile",
            403,
            markers,
        )
    return AuthorityTestModeStatus(True, "Authority test mode is enabled", 200, markers)


def validate_authority_test_token(
    provided: str,
    *,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    current = _normalized_env(env)
    expected = str(current.get(TEST_TOKEN_ENV) or "").strip()
    if not expected:
        return {
            "success": False,
            "error": "Authority test token is not configured",
            "status_code": 404,
        }
    if not str(provided or "").strip():
        return {
            "success": False,
            "error": "Authority test token is required",
            "status_code": 401,
        }
    if not hmac.compare_digest(str(provided), expected):
        return {
            "success": False,
            "error": "Authority test token is invalid",
            "status_code": 403,
        }
    return {"success": True}


def load_authority_test_policy(
    policy: dict[str, Any] | None = None,
    *,
    policy_path: str | Path | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    if isinstance(policy, dict):
        return dict(policy)
    path_value = str(policy_path or _normalized_env(env).get(TEST_POLICY_ENV) or "").strip()
    if not path_value:
        return {"version": 1, "rules": []}
    try:
        payload = json.loads(Path(path_value).expanduser().read_text(encoding="utf-8"))
    except OSError as exc:
        return {"version": 1, "rules": [], "_error": f"Authority test policy could not be read: {exc}"}
    except json.JSONDecodeError as exc:
        return {"version": 1, "rules": [], "_error": f"Authority test policy is not valid JSON: {exc}"}
    return payload if isinstance(payload, dict) else {"version": 1, "rules": [], "_error": "Authority test policy must be an object"}


def _decision(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in _APPROVE:
        return "approve"
    if raw in _DENY:
        return "deny"
    if raw in _TIMEOUT:
        return "timeout"
    if raw in _CANCEL:
        return "cancel"
    if raw in _REQUIRE_SYNTHETIC:
        return "require_synthetic"
    return ""


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _resource_matches(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    for key, expected_value in sanitize_authority_resource(expected).items():
        if key not in actual:
            return False
        actual_value = actual.get(key)
        if isinstance(expected_value, dict):
            if not isinstance(actual_value, dict) or not _resource_matches(expected_value, actual_value):
                return False
        elif actual_value != expected_value:
            return False
    return True


def _rule_matches(
    rule: dict[str, Any],
    request: AuthorityRequest,
    *,
    scenario_id: str,
) -> bool:
    if scenario_id and str(rule.get("scenario_id") or "").strip() not in {"", scenario_id}:
        return False
    request_id = str(rule.get("request_id") or "").strip()
    if request_id and request_id != request.request_id:
        return False
    if str(rule.get("permission_id") or "").strip() != request.permission_id:
        return False
    principal_id = str(rule.get("principal_id") or "").strip()
    if principal_id and principal_id != request.principal_id:
        return False
    resource = rule.get("resource") if isinstance(rule.get("resource"), dict) else {}
    if not resource:
        return False
    return _resource_matches(resource, request.resource)


def _select_rule(
    request: AuthorityRequest,
    *,
    policy: dict[str, Any],
    rule: dict[str, Any] | None,
    scenario_id: str,
) -> tuple[dict[str, Any] | None, str]:
    if isinstance(policy.get("_error"), str):
        return None, policy["_error"]
    candidates: list[dict[str, Any]] = []
    if isinstance(rule, dict):
        candidates.append(dict(rule))
    raw_rules = policy.get("rules")
    if isinstance(raw_rules, list):
        candidates.extend(dict(item) for item in raw_rules if isinstance(item, dict))
    for candidate in candidates:
        if not _decision(candidate.get("decision") or candidate.get("settlement") or candidate.get("action")):
            continue
        if _rule_matches(candidate, request, scenario_id=scenario_id):
            return candidate, ""
    return None, "No Authority test policy rule matched this request"


def _audit(service: Any, action: str, details: dict[str, Any]) -> None:
    store = getattr(service, "_request_store", None)
    audit = getattr(store, "audit", None)
    if callable(audit):
        audit(action, details)


def _resource_hash(service: Any, resource: dict[str, Any]) -> str:
    store = getattr(service, "_request_store", None)
    resource_hash = getattr(store, "resource_hash", None)
    if callable(resource_hash):
        return str(resource_hash(resource))
    return ""


def _get_request(service: Any, request_id: str) -> AuthorityRequest | None:
    store = getattr(service, "_request_store", None)
    get_request = getattr(store, "get_request", None)
    if callable(get_request):
        return get_request(request_id)
    result = service.get_request(request_id, actor_principal={"core_role": True})
    request = result.get("request") if isinstance(result, dict) else None
    return AuthorityRequest.from_dict(request) if isinstance(request, dict) else None


def _authority_followups(result: dict[str, Any], *, scenario_id: str) -> list[dict[str, Any]]:
    followups: list[dict[str, Any]] = []
    if str(result.get("token") or "").strip():
        followups.append(
            {
                "request_id": result.get("request_id"),
                "permission_id": result.get("permission_id"),
                "approval_token": result.get("token"),
                "authority_mode": "test",
                "scenario_id": scenario_id or None,
            }
        )
    for related in result.get("related_approvals") or []:
        if not isinstance(related, dict) or not str(related.get("token") or "").strip():
            continue
        followups.append(
            {
                "request_id": related.get("request_id"),
                "permission_id": related.get("permission_id"),
                "approval_token": related.get("token"),
                "authority_mode": "test",
                "scenario_id": scenario_id or None,
            }
        )
    return followups


def _expire_pending_request(service: Any, request: AuthorityRequest) -> dict[str, Any]:
    store = getattr(service, "_request_store", None)
    expire_pending_request = getattr(store, "expire_pending_request", None)
    if callable(expire_pending_request):
        return expire_pending_request(request.request_id, reason="authority_test_synthetic_timeout")
    if request.status != "pending":
        return {"settled": False, "request": request, "reason": "not_pending"}
    updated = store.set_request_status(request.request_id, "expired") if store is not None else None
    return {"settled": updated is not None, "request": updated or request, "reason": ""}


def settle_authority_test_request(
    service: Any,
    request_id: str,
    *,
    policy: dict[str, Any] | None = None,
    policy_path: str | Path | None = None,
    rule: dict[str, Any] | None = None,
    scenario_id: str = "",
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Settle a pending Authority request under an explicit QA policy rule."""
    status = authority_test_mode_status(env)
    if not status.enabled:
        return status.to_error()

    request_id = str(request_id or "").strip()
    if not request_id:
        return {"success": False, "error": "request_id is required", "status_code": 400, "authority_mode": "test"}

    request = _get_request(service, request_id)
    if request is None:
        return {
            "success": False,
            "error": "Authority request not found",
            "status_code": 404,
            "authority_mode": "test",
        }
    if request.status != "pending":
        return {
            "success": False,
            "error": f"Authority request is {request.status}",
            "status_code": 409,
            "authority_mode": "test",
            "request_id": request.request_id,
        }

    loaded_policy = load_authority_test_policy(policy, policy_path=policy_path, env=env)
    selected_rule, rule_error = _select_rule(
        request,
        policy=loaded_policy,
        rule=rule,
        scenario_id=str(scenario_id or ""),
    )
    if selected_rule is None:
        _audit(
            service,
            "authority_test_harness_policy_mismatch",
            {
                "authority_mode": "test",
                "request_id": request.request_id,
                "permission_id": request.permission_id,
                "resource_hash": _resource_hash(service, request.resource),
                "scenario_id": str(scenario_id or ""),
                "reason": rule_error,
            },
        )
        return {
            "success": False,
            "error": rule_error,
            "status_code": 412,
            "authority_mode": "test",
            "request_id": request.request_id,
        }

    decision = _decision(
        selected_rule.get("decision")
        or selected_rule.get("settlement")
        or selected_rule.get("action")
    )
    rule_id = str(selected_rule.get("rule_id") or selected_rule.get("id") or "").strip()
    scenario = str(scenario_id or selected_rule.get("scenario_id") or "").strip()
    audit_base = {
        "authority_mode": "test",
        "request_id": request.request_id,
        "permission_id": request.permission_id,
        "resource_hash": _resource_hash(service, request.resource),
        "decision": decision,
        "rule_id": rule_id,
        "scenario_id": scenario,
    }
    _audit(service, "authority_test_harness_settlement_requested", audit_base)

    if decision == "require_synthetic":
        _audit(service, "authority_test_harness_synthetic_required", audit_base)
        return {
            "success": False,
            "error": "Authority test policy requires explicit synthetic settlement",
            "status_code": 409,
            "authority_mode": "test",
            "request_id": request.request_id,
            "decision": decision,
        }

    if decision == "timeout":
        settlement = _expire_pending_request(service, request)
        if not settlement.get("settled"):
            current = settlement.get("request")
            current_status = getattr(current, "status", "pending")
            return {
                "success": False,
                "error": f"Authority request is {current_status}",
                "status_code": 409,
                "authority_mode": "test",
                "request_id": request.request_id,
                "decision": decision,
            }
        _audit(service, "authority_test_harness_settled", {**audit_base, "status": "expired"})
        return {
            "success": True,
            "authority_mode": "test",
            "request_id": request.request_id,
            "decision": decision,
            "expired": True,
            "status": "expired",
        }

    ui_operator = sign_ui_operator(
        request.request_id,
        nonce="authority-test:{}:{}:{}".format(scenario or "default", rule_id or "rule", request.request_id),
    )
    if decision == "approve":
        config = selected_rule.get("config") if isinstance(selected_rule.get("config"), dict) else None
        result = service.approve_request(
            request.request_id,
            scope=str(selected_rule.get("scope") or "once"),
            config=config,
            expires_in_seconds=_optional_int(selected_rule.get("expires_in_seconds")),
            related_permissions=_string_list(selected_rule.get("related_permissions")),
            ui_operator=ui_operator,
            actor_principal={"core_role": True},
        )
        if not result.get("success"):
            _audit(service, "authority_test_harness_settle_failed", {**audit_base, "error": result.get("error")})
            result = dict(result)
            result["authority_mode"] = "test"
            result.setdefault("decision", decision)
            return result
        followups = _authority_followups(result, scenario_id=scenario)
        _audit(
            service,
            "authority_test_harness_settled",
            {
                **audit_base,
                "status": "approved",
                "scope": result.get("scope"),
                "followup_count": len(followups),
            },
        )
        return {
            **result,
            "authority_mode": "test",
            "decision": decision,
            "authority_followup": followups[0] if followups else None,
            "authority_followups": followups,
        }

    result = service.deny_request(
        request.request_id,
        reason=str(selected_rule.get("reason") or ("synthetic cancel" if decision == "cancel" else "synthetic deny")),
        persist=bool(selected_rule.get("persist")),
        ui_operator=ui_operator,
        actor_principal={"core_role": True},
    )
    if not result.get("success"):
        _audit(service, "authority_test_harness_settle_failed", {**audit_base, "error": result.get("error")})
        result = dict(result)
        result["authority_mode"] = "test"
        result.setdefault("decision", decision)
        return result
    _audit(service, "authority_test_harness_settled", {**audit_base, "status": "denied"})
    return {
        **result,
        "authority_mode": "test",
        "decision": decision,
        "cancelled": decision == "cancel",
    }
