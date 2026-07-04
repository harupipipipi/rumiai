from __future__ import annotations

import re
from typing import Any


ERROR_CATEGORIES = {"target", "route", "queue", "timeout", "policy", "unknown"}

_MENTION_RE = re.compile(r"@([A-Za-z][A-Za-z0-9_-]{1,63})")
_DEFAULT_TARGETS = {
    "browser_qa",
    "client_manager",
    "coder",
    "coding_engineer",
    "project_manager",
    "pm",
    "reviewer",
    "scheduler",
    "searcher",
    "toolsmith",
}
_TARGET_ALIASES = {
    "coding": "coding_engineer",
    "engineer": "coding_engineer",
    "qa": "browser_qa",
    "review": "reviewer",
    "tooling": "toolsmith",
}


class SubagentDelegationError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        category: str,
        code: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.category = _clean_category(category)
        self.code = str(code or "SUBAGENT_DELEGATION_FAILED").strip() or "SUBAGENT_DELEGATION_FAILED"
        self.details = details if isinstance(details, dict) else {}

    def to_error(self) -> dict[str, Any]:
        return {
            "type": "subagent_delegation_error",
            "category": self.category,
            "code": self.code,
            "message": str(self),
            "details": dict(self.details),
            "actionable_hint": actionable_hint(self.category, self.code, self.details),
        }

    def to_result(self) -> dict[str, Any]:
        return {
            "status": "error",
            "code": self.code,
            "error": str(self),
            "delegation_error": self.to_error(),
        }


def available_subagent_targets(context: dict[str, Any] | None = None) -> list[str]:
    targets: set[str] = set(_DEFAULT_TARGETS)
    context = context if isinstance(context, dict) else {}
    for value in context.get("available_subagent_targets") or context.get("available_targets") or []:
        cleaned = _clean_target(value)
        if cleaned:
            targets.add(cleaned)
    policy = context.get("profile_policy") if isinstance(context.get("profile_policy"), dict) else {}
    role_overrides = policy.get("role_overrides") if isinstance(policy.get("role_overrides"), dict) else {}
    for value in role_overrides.keys():
        cleaned = _clean_target(value)
        if cleaned:
            targets.add(cleaned)
    try:
        from domain.agent.role_registry import RoleRegistry

        for role in RoleRegistry().list_roles():
            if not isinstance(role, dict):
                continue
            for key in ("role_key", "agent_id"):
                cleaned = _clean_target(role.get(key))
                if cleaned:
                    targets.add(cleaned)
    except Exception:
        pass
    return sorted(targets)


def resolve_subagent_target(
    arguments: dict[str, Any] | None,
    context: dict[str, Any] | None,
    task: str,
) -> dict[str, Any]:
    arguments = arguments if isinstance(arguments, dict) else {}
    context = context if isinstance(context, dict) else {}
    available = set(available_subagent_targets(context))
    explicit = _explicit_target(arguments)
    if explicit:
        return {
            "agent_id": explicit,
            "source": "argument",
            "requested": explicit,
            "mentions": _mentions(task),
            "available_targets": sorted(available),
        }

    mentions = _mentions(task)
    known_mentions = [_canonical_target(item) for item in mentions if _canonical_target(item) in available]
    unknown_mentions = [item for item in mentions if _canonical_target(item) not in available]
    if len(known_mentions) == 1 and not unknown_mentions:
        return {
            "agent_id": known_mentions[0],
            "source": "mention",
            "requested": mentions[0],
            "mentions": mentions,
            "available_targets": sorted(available),
        }
    if len(known_mentions) > 1:
        raise SubagentDelegationError(
            "Subagent delegation target is ambiguous; pass agent_id explicitly.",
            category="target",
            code="SUBAGENT_TARGET_AMBIGUOUS",
            details={
                "mentions": mentions,
                "matched_targets": known_mentions,
                "available_targets": sorted(available),
            },
        )
    if mentions:
        raise SubagentDelegationError(
            "Unknown subagent target persona: @" + mentions[0],
            category="target",
            code="SUBAGENT_TARGET_UNKNOWN",
            details={
                "mentions": mentions,
                "unknown_targets": unknown_mentions or mentions,
                "available_targets": sorted(available),
            },
        )

    fallback = _clean_target(context.get("agent_id")) or "subagent"
    return {
        "agent_id": fallback,
        "source": "context" if fallback != "subagent" else "default",
        "requested": fallback,
        "mentions": [],
        "available_targets": sorted(available),
    }


def classify_delegation_result(
    result: Any,
    *,
    route: str,
    target_agent_id: str = "",
) -> SubagentDelegationError:
    code = _result_code(result) or "SUBAGENT_DELEGATION_FAILED"
    message = _result_message(result) or "subagent delegation failed"
    details = {
        "route": route,
        "target_agent_id": target_agent_id,
        "status": result.get("status") if isinstance(result, dict) else None,
        "code": code,
    }
    return SubagentDelegationError(
        message,
        category=_category_from_code_message(code, message),
        code=_normalize_error_code(code),
        details={key: value for key, value in details.items() if value not in (None, "")},
    )


def classify_exception(
    exc: BaseException,
    *,
    route: str,
    target_agent_id: str = "",
) -> SubagentDelegationError:
    if isinstance(exc, SubagentDelegationError):
        return exc
    message = str(exc) or exc.__class__.__name__
    code = exc.__class__.__name__.upper()
    return SubagentDelegationError(
        message,
        category=_category_from_code_message(code, message),
        code=_normalize_error_code(code),
        details={"route": route, "target_agent_id": target_agent_id, "exception_type": exc.__class__.__name__},
    )


def delegation_status(result: dict[str, Any], *, route: str, target_agent_id: str = "") -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None
    status = _nested_status(result)
    if not status:
        return None
    category = "queue" if status in {"created", "queued", "running", "waiting_approval", "waiting_user_input"} else "completed"
    payload = {
        "type": "subagent_delegation_status",
        "category": category,
        "status": status,
        "route": route,
        "target_agent_id": target_agent_id,
    }
    execution_id = _nested_execution_id(result)
    if execution_id:
        payload["execution_id"] = execution_id
    if category == "queue":
        payload["actionable_hint"] = "Delegation was accepted but is not complete yet; inspect the execution_id and approval queue."
    return payload


def tool_error_result(error: SubagentDelegationError) -> dict[str, Any]:
    delegation_error = error.to_error()
    return {
        "result": delegation_error["message"],
        "is_error": True,
        "widget": {
            "type": "subagent",
            "status": "error",
            "delegation_error": delegation_error,
        },
        "delegation_error": delegation_error,
    }


def error_from_capability_response(response: Any, *, route: str = "function.call") -> SubagentDelegationError:
    code = str(getattr(response, "error_type", "") or "SUBAGENT_CAPABILITY_FAILED")
    message = str(getattr(response, "error", "") or "subagent capability execution failed")
    return SubagentDelegationError(
        message,
        category=_category_from_code_message(code, message),
        code=_normalize_error_code(code),
        details={"route": route, "capability_error_type": code},
    )


def actionable_hint(category: str, code: str, details: dict[str, Any] | None = None) -> str:
    details = details if isinstance(details, dict) else {}
    if category == "target":
        available = details.get("available_targets") if isinstance(details.get("available_targets"), list) else []
        suffix = ": " + ", ".join(str(item) for item in available[:8]) if available else ""
        return "Use a known persona or pass agent_id explicitly" + suffix + "."
    if category == "route":
        return "Check the input delivery action and registered route for this delegation."
    if category == "queue":
        return "Inspect the delegated execution and approval queue; retry only after the queued run advances or is cancelled."
    if category == "timeout":
        return "Increase the subagent timeout or reduce the delegated task scope; the child run did not return in time."
    if category == "policy":
        return "Check tool policy, approval state, caller requirements, and capability grants for subagent."
    return "Inspect the delegation_error details and retry with a smaller explicit task."


def _explicit_target(arguments: dict[str, Any]) -> str:
    for key in ("agent_id", "target_agent_id", "target_persona", "persona_id", "role_key"):
        cleaned = _clean_target(arguments.get(key))
        if cleaned:
            return _canonical_target(cleaned)
    target = arguments.get("target") if isinstance(arguments.get("target"), dict) else {}
    return _canonical_target(_clean_target(target.get("agent_id") or target.get("persona_id")))


def _mentions(text: str) -> list[str]:
    seen: set[str] = set()
    values: list[str] = []
    for match in _MENTION_RE.finditer(str(text or "")):
        cleaned = _clean_target(match.group(1))
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            values.append(cleaned)
    return values


def _canonical_target(value: Any) -> str:
    cleaned = _clean_target(value)
    return _TARGET_ALIASES.get(cleaned, cleaned)


def _clean_target(value: Any) -> str:
    text = str(value or "").strip().lstrip("@").lower().replace("-", "_")
    return re.sub(r"[^a-z0-9_]", "", text)


def _clean_category(category: str) -> str:
    cleaned = str(category or "").strip().lower()
    return cleaned if cleaned in ERROR_CATEGORIES else "unknown"


def _normalize_error_code(code: Any) -> str:
    text = str(code or "").strip().upper().replace(".", "_").replace("-", "_")
    if not text:
        return "SUBAGENT_DELEGATION_FAILED"
    if text.startswith("SUBAGENT_"):
        return text
    return "SUBAGENT_" + text


def _result_code(result: Any) -> str:
    if not isinstance(result, dict):
        return ""
    error = result.get("error") if isinstance(result.get("error"), dict) else {}
    return str(result.get("code") or error.get("code") or result.get("error_type") or "")


def _result_message(result: Any) -> str:
    if isinstance(result, dict):
        error = result.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error.get("code") or "")
        if error not in (None, ""):
            return str(error)
        nested = result.get("result") if isinstance(result.get("result"), dict) else {}
        if nested.get("error"):
            return str(nested.get("error"))
    return str(result or "")


def _category_from_code_message(code: Any, message: Any) -> str:
    text = (str(code or "") + " " + str(message or "")).lower()
    if "timeout" in text or "timed out" in text:
        return "timeout"
    if any(marker in text for marker in ("permission", "policy", "approval", "caller_requires", "requires_denied", "grant", "denied", "not connected")):
        return "policy"
    if any(marker in text for marker in ("queue", "queued", "busy", "stale", "waiting_approval", "waiting user")):
        return "queue"
    if any(marker in text for marker in ("target", "persona", "parent conversation", "unknown subagent role")):
        return "target"
    if any(marker in text for marker in ("route", "dispatch", "unknown_input_action", "function_not_found", "registry")):
        return "route"
    return "unknown"


def _nested_status(result: dict[str, Any]) -> str:
    for key in ("delegate", "result", "data"):
        nested = result.get(key)
        if isinstance(nested, dict):
            status = str(nested.get("status") or "").strip().lower()
            if status:
                return status
    return str(result.get("status") or "").strip().lower()


def _nested_execution_id(result: dict[str, Any]) -> str:
    for key in ("delegate", "result", "data"):
        nested = result.get(key)
        if isinstance(nested, dict):
            value = str(nested.get("execution_id") or "").strip()
            if value:
                return value
    return str(result.get("execution_id") or "").strip()
