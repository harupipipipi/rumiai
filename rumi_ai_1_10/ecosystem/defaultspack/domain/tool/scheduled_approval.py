from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit


_MIMO_CODING_COMPANY_PROFILE_ID = "defaultspack.mimo_coding_company"
_MIMO_CODING_COMPANY_ID = "mimo-coding-company"
_ROUTE_IDENTITY_RE = re.compile(
    r"^(?:rumi_api\s*[:.]?\s*)?(?P<method>GET|POST|PUT|PATCH|DELETE)\s+(?P<path>/\S+)$",
    re.IGNORECASE,
)
_DESKTOP_FRAME_PATH_RE = re.compile(r"^/api/desktops/[^/]+/frame$")
_DESKTOP_FRAME_TEMPLATES = ("/api/desktops/{id}/frame", "/api/desktops/{seat_id}/frame")
_APPROVAL_REQUIRED_FINISH_REASONS = {"approval_required", "authority_approval_required"}
_DISPLAY_TOOL_ALIASES = {
    "desktop_list": "desktop_list",
    "desktop_create": "desktop_create",
    "desktop_frame": "desktop_frame",
    "managed_runtime_desktop_frame": "desktop_frame",
    "desktop_input": "desktop_input",
    "managed_runtime_desktop_input": "desktop_input",
}


def _mimo_schedule_auto_approval_enabled(task_cfg: dict[str, Any]) -> bool:
    policy = task_cfg.get("tool_policy") if isinstance(task_cfg.get("tool_policy"), dict) else {}
    metadata = task_cfg.get("metadata") if isinstance(task_cfg.get("metadata"), dict) else {}
    profile_id = str(task_cfg.get("profile_id") or policy.get("profile_id") or metadata.get("profile_id") or "").strip()
    company_id = str(metadata.get("company_id") or "").strip()
    return (
        bool(policy.get("schedule_auto_approve_tool_requests"))
        and profile_id == _MIMO_CODING_COMPANY_PROFILE_ID
        and company_id == _MIMO_CODING_COMPANY_ID
    )


def _schedule_auto_approval_allowlist(task_cfg: dict[str, Any]) -> set[str]:
    policy = task_cfg.get("tool_policy") if isinstance(task_cfg.get("tool_policy"), dict) else {}
    raw = policy.get("schedule_auto_approve_tool_allowlist")
    if not isinstance(raw, list):
        raw = []
    allowlist: set[str] = set()
    for item in raw:
        text = str(item).strip()
        if text:
            allowlist.update(_identity_variants(text))
    return allowlist


def _identity_variants(value: str) -> set[str]:
    text = str(value or "").strip()
    if not text:
        return set()
    variants = {text}
    normalized = _normalize_identity_text(text)
    if normalized:
        variants.add(normalized)
        canonical = _canonical_tool_name(normalized)
        if canonical != normalized:
            variants.add(canonical)
    match = _ROUTE_IDENTITY_RE.match(text)
    if match:
        variants.update(_route_identity_variants(match.group("method"), match.group("path")))
    return variants


def _canonical_tool_name(value: Any) -> str:
    text = str(value or "").strip()
    normalized = _normalize_identity_text(text)
    return _DISPLAY_TOOL_ALIASES.get(normalized, text)


def _normalize_identity_text(value: str) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def _identity_text_matches(left: Any, right: Any) -> bool:
    left_text = str(left or "").strip()
    right_text = str(right or "").strip()
    if not left_text or not right_text:
        return False
    if left_text == right_text:
        return True
    return _normalize_identity_text(left_text) == _normalize_identity_text(right_text)


def _normalize_route_path(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = urlsplit(text)
    path = parsed.path if parsed.scheme or parsed.netloc else text
    if "?" in path:
        path = path.split("?", 1)[0]
    path = path.strip()
    if len(path) > 1:
        path = path.rstrip("/")
    return path


def _request_method(payload: dict[str, Any]) -> str:
    return str(payload.get("method") or payload.get("_method") or "GET").strip().upper()


def _request_path(payload: dict[str, Any]) -> str:
    for key in ("path", "route_path", "url", "uri", "endpoint"):
        path = _normalize_route_path(payload.get(key))
        if path:
            return path
    return ""


def _route_identity_variants(method: Any, path: Any) -> set[str]:
    normalized_method = str(method or "GET").strip().upper()
    normalized_path = _normalize_route_path(path)
    if not normalized_method or not normalized_path.startswith("/"):
        return set()
    variants = {
        f"{normalized_method} {normalized_path}",
        f"rumi_api {normalized_method} {normalized_path}",
        f"rumi_api:{normalized_method} {normalized_path}",
    }
    if _DESKTOP_FRAME_PATH_RE.match(normalized_path):
        for template in _DESKTOP_FRAME_TEMPLATES:
            variants.update(
                {
                    f"{normalized_method} {template}",
                    f"rumi_api {normalized_method} {template}",
                    f"rumi_api:{normalized_method} {template}",
                }
            )
        if normalized_method == "GET":
            variants.update({"desktop_frame", "managed_runtime_desktop_frame"})
    return variants


def _payload_mappings(*values: Any) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    seen: set[int] = set()
    for value in values:
        if not isinstance(value, dict):
            continue
        marker = id(value)
        if marker not in seen:
            seen.add(marker)
            payloads.append(value)
    return payloads


def _approval_identity_candidates(
    *,
    tool_name: str,
    operation: str,
    stored_operation: str,
    details: dict[str, Any],
    pending: dict[str, Any],
) -> set[str]:
    candidates: set[str] = set()
    for value in (
        tool_name,
        operation,
        stored_operation,
        details.get("action"),
        details.get("function_id"),
        pending.get("action"),
        pending.get("operation"),
    ):
        candidates.update(_identity_variants(str(value or "").strip()))

    payloads = _payload_mappings(
        details.get("arguments"),
        pending.get("payload"),
        pending.get("arguments"),
    )
    for payload in payloads:
        handler = str(payload.get("_handler") or "").strip()
        if handler:
            candidates.add(handler)
        if tool_name == "rumi_api":
            rumi_action = str(payload.get("action") or "").strip()
            if rumi_action:
                candidates.update(
                    {
                        rumi_action,
                        f"rumi_api {rumi_action}",
                        f"rumi_api:{rumi_action}",
                    }
                )
            path = _request_path(payload)
            if path:
                candidates.update(_route_identity_variants(_request_method(payload), path))
    return candidates


def _first_text_value(source: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = str(source.get(key) or "").strip()
        if value:
            return value
    return ""


def _is_approval_required_mapping(value: dict[str, Any]) -> bool:
    if value.get("approval_required") is True or value.get("requires_approval") is True:
        return True
    status = str(value.get("status") or value.get("state") or value.get("finish_reason") or "").strip().lower()
    return status in {"approval_required", "requires_approval", "pending_approval"}


def _nested_payload_mapping(value: dict[str, Any]) -> dict[str, Any]:
    for key in ("arguments", "payload", "input", "params"):
        payload = value.get(key)
        if isinstance(payload, dict):
            return payload
    return {}


def _pending_approval_from_mapping(value: dict[str, Any]) -> dict[str, Any] | None:
    if not _is_approval_required_mapping(value):
        return None

    approval_request = value.get("approval_request")
    if isinstance(approval_request, dict):
        request_id = _first_text_value(approval_request, ("request_id", "approval_request_id", "approval_id", "id"))
    else:
        request_id = ""
    request_id = request_id or _first_text_value(value, ("approval_request_id", "request_id", "approval_id"))
    if not request_id:
        return None

    tool_name = _first_text_value(
        value,
        ("tool_name", "name", "tool", "tool_ref", "function_name", "display_name", "title", "label"),
    )
    tool_name = _canonical_tool_name(tool_name)
    operation = _first_text_value(value, ("operation", "action", "function_id", "tool_ref"))
    payload = _nested_payload_mapping(value)
    pending = {
        "tool_name": tool_name,
        "tool_call_id": _first_text_value(value, ("tool_call_id", "id", "call_id")),
        "action": operation,
        "operation": operation,
        "payload": payload,
        "arguments": payload,
        "approval_required": True,
        "requires_approval": True,
        "approval_request_id": request_id,
        "request_id": request_id,
        "expires_at": value.get("expires_at"),
        "risk_level": value.get("risk_level"),
        "display_summary": value.get("display_summary") or value.get("summary"),
    }
    return {key: item for key, item in pending.items() if item not in ("", None)}


def _walk_approval_mappings(value: Any, *, _seen: set[int] | None = None):
    seen = _seen if _seen is not None else set()
    if isinstance(value, dict):
        marker = id(value)
        if marker in seen:
            return
        seen.add(marker)
        yield value
        for nested in value.values():
            yield from _walk_approval_mappings(nested, _seen=seen)
    elif isinstance(value, list):
        marker = id(value)
        if marker in seen:
            return
        seen.add(marker)
        for item in value:
            yield from _walk_approval_mappings(item, _seen=seen)


def pending_scheduled_approval_from_chat_result(result: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(result, dict) or result.get("status") != "ok":
        return None
    data = result.get("data")
    if not isinstance(data, dict):
        return None
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    for pending in (
        metadata.get("pending_approval"),
        metadata.get("pendingApproval"),
        metadata.get("pendingAuthorityApproval"),
        data.get("pending_approval"),
        data.get("pendingApproval"),
        data.get("pendingAuthorityApproval"),
    ):
        if isinstance(pending, dict):
            normalized = _pending_approval_from_mapping(pending)
            return normalized or pending

    events = data.get("events") if isinstance(data.get("events"), list) else []
    for event in reversed(events):
        if not isinstance(event, dict):
            continue
        event_type = str(event.get("type") or event.get("phase") or "").strip()
        if event_type == "approval_requested":
            for key in ("data", "details"):
                event_data = event.get(key)
                if isinstance(event_data, dict):
                    normalized = _pending_approval_from_mapping(event_data)
                    return normalized or event_data
            if event.get("approval_required") or event.get("requires_approval"):
                normalized = _pending_approval_from_mapping(event)
                return normalized or event
        for mapping in _walk_approval_mappings(event):
            normalized = _pending_approval_from_mapping(mapping)
            if normalized:
                return normalized

    for mapping in _walk_approval_mappings(data):
        normalized = _pending_approval_from_mapping(mapping)
        if normalized:
            return normalized
    return None


def current_scheduled_approval_from_conversation(
    conversation: dict[str, Any] | None,
    *,
    schedule_id: str,
) -> dict[str, Any] | None:
    if not isinstance(conversation, dict):
        return None
    messages = conversation.get("messages")
    if not isinstance(messages, list) or not messages:
        return None
    messages_by_id = {
        str(message.get("id") or ""): message
        for message in messages
        if isinstance(message, dict) and str(message.get("id") or "").strip()
    }
    current_id = str(conversation.get("current_node_id") or "").strip()
    current = messages_by_id.get(current_id)
    if not isinstance(current, dict):
        return None
    if str(current.get("role") or "") != "assistant":
        return None
    if str(current.get("finish_reason") or "").strip() not in _APPROVAL_REQUIRED_FINISH_REASONS:
        return None

    result = {"status": "ok", "data": current}
    if not isinstance(pending_scheduled_approval_from_chat_result(result), dict):
        return None

    parent_id = str(current.get("parent_id") or "").strip()
    parent = messages_by_id.get(parent_id)
    if not isinstance(parent, dict) or str(parent.get("role") or "") != "user":
        return None
    source_metadata = parent.get("metadata") if isinstance(parent.get("metadata"), dict) else {}
    source = str(source_metadata.get("source") or "").strip()
    if source not in {"scheduler", "scheduler_approval_followup"}:
        return None
    if str(source_metadata.get("schedule_id") or "").strip() != str(schedule_id or "").strip():
        return None
    return {"result": result, "source_metadata": dict(source_metadata)}


def _approval_summary_operation(
    *,
    tool_name: str,
    stored_operation: str,
    details: dict[str, Any],
    pending: dict[str, Any],
) -> str:
    if tool_name == "rumi_api":
        for payload in _payload_mappings(details.get("arguments"), pending.get("payload"), pending.get("arguments")):
            path = _request_path(payload)
            if not path:
                continue
            method = _request_method(payload)
            if _DESKTOP_FRAME_PATH_RE.match(path):
                return f"{method} /api/desktops/{{id}}/frame"
            return f"{method} {path}"
    return stored_operation


def _without_approval_token(value: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(value or {})
    cleaned.pop("approval_token", None)
    return cleaned


def _approval_followup_arguments(
    *,
    tool_name: str,
    action: str,
    details: dict[str, Any],
    pending: dict[str, Any],
) -> dict[str, Any]:
    for source in (details.get("arguments"), pending.get("arguments")):
        if isinstance(source, dict):
            return _without_approval_token(source)

    payload = pending.get("payload")
    if not isinstance(payload, dict):
        payload = details.get("payload")
    if not isinstance(payload, dict):
        return {}

    cleaned_payload = _without_approval_token(payload)
    if tool_name == "browser_computer":
        return {"action": action, "payload": cleaned_payload}
    if tool_name in {"browser_use", "computer_use"}:
        return {"action": action, **cleaned_payload}
    return cleaned_payload


def approve_schedule_pending_approval(
    task_cfg: dict[str, Any],
    pending: dict[str, Any],
    *,
    conversation_id: str,
) -> dict[str, Any] | None:
    if not _mimo_schedule_auto_approval_enabled(task_cfg):
        return None
    request_id = str(pending.get("approval_request_id") or pending.get("request_id") or "").strip()
    tool_name = _canonical_tool_name(pending.get("tool_name"))
    operation = str(pending.get("operation") or pending.get("action") or "").strip()
    if not request_id or not tool_name:
        return None

    try:
        from domain.safety import approval
    except Exception:
        return None

    request = approval.get_approval_request(request_id)
    if not isinstance(request, dict):
        return None
    request_status = str(request.get("status") or "").strip().lower()
    # The manager can approve between approval_required and scheduler follow-up;
    # approve() will mint a fresh one-shot token for an approved request.
    if request_status not in {"pending", "approved"}:
        return None
    details = request.get("details") if isinstance(request.get("details"), dict) else {}
    stored_conversation_id = str(details.get("conversation_id") or "").strip()
    if stored_conversation_id and stored_conversation_id != str(conversation_id or "").strip():
        return None
    stored_tool_name = str(details.get("tool_name") or "").strip()
    if stored_tool_name and not _identity_text_matches(stored_tool_name, tool_name):
        return None

    stored_operation = str(request.get("operation") or operation or "").strip()
    allowlist = _schedule_auto_approval_allowlist(task_cfg)
    identity_candidates = _approval_identity_candidates(
        tool_name=tool_name,
        operation=operation,
        stored_operation=stored_operation,
        details=details,
        pending=pending,
    )
    if allowlist and not allowlist.intersection(identity_candidates):
        return None

    decision = approval.approve(request_id)
    if not isinstance(decision, dict) or not decision.get("approved") or not decision.get("token"):
        return None
    token = str(decision.get("token") or "").strip()
    summary_operation = _approval_summary_operation(
        tool_name=tool_name,
        stored_operation=stored_operation,
        details=details,
        pending=pending,
    )
    action = str(pending.get("action") or stored_operation or "").strip()
    return {
        "summary": {
            "request_id": request_id,
            "tool_name": tool_name,
            "operation": summary_operation,
            "status": "approved",
        },
        "followup": {
            "request_id": request_id,
            "approval_request_id": request_id,
            "approval_token": token,
            "tool_name": tool_name,
            "tool_call_id": pending.get("tool_call_id"),
            "action": action,
            "operation": stored_operation,
            "arguments": _approval_followup_arguments(
                tool_name=tool_name,
                action=action,
                details=details,
                pending=pending,
            ),
        },
    }
