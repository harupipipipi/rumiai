from __future__ import annotations

from typing import Any


_MIMO_CODING_COMPANY_PROFILE_ID = "defaultspack.mimo_coding_company"
_MIMO_CODING_COMPANY_ID = "mimo-coding-company"


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
    return {str(item).strip() for item in raw if str(item).strip()}


def approve_schedule_pending_approval(
    task_cfg: dict[str, Any],
    pending: dict[str, Any],
    *,
    conversation_id: str,
) -> dict[str, Any] | None:
    if not _mimo_schedule_auto_approval_enabled(task_cfg):
        return None
    request_id = str(pending.get("approval_request_id") or pending.get("request_id") or "").strip()
    tool_name = str(pending.get("tool_name") or "").strip()
    operation = str(pending.get("operation") or pending.get("action") or "").strip()
    if not request_id or not tool_name:
        return None

    try:
        from domain.safety import approval
    except Exception:
        return None

    request = approval.get_approval_request(request_id)
    if not isinstance(request, dict) or str(request.get("status") or "") != "pending":
        return None
    details = request.get("details") if isinstance(request.get("details"), dict) else {}
    stored_conversation_id = str(details.get("conversation_id") or "").strip()
    if stored_conversation_id and stored_conversation_id != str(conversation_id or "").strip():
        return None
    stored_tool_name = str(details.get("tool_name") or "").strip()
    if stored_tool_name and stored_tool_name != tool_name:
        return None

    stored_operation = str(request.get("operation") or operation or "").strip()
    allowlist = _schedule_auto_approval_allowlist(task_cfg)
    if allowlist and tool_name not in allowlist and stored_operation not in allowlist:
        return None

    decision = approval.approve(request_id)
    if not isinstance(decision, dict) or not decision.get("approved") or not decision.get("token"):
        return None
    token = str(decision.get("token") or "").strip()
    return {
        "summary": {
            "request_id": request_id,
            "tool_name": tool_name,
            "operation": stored_operation,
            "status": "approved",
        },
        "followup": {
            "request_id": request_id,
            "approval_request_id": request_id,
            "approval_token": token,
            "tool_name": tool_name,
            "tool_call_id": pending.get("tool_call_id"),
            "action": pending.get("action") or stored_operation,
            "operation": stored_operation,
        },
    }
