from __future__ import annotations

from typing import Any

from core_runtime.operating_profile import OperatingProfilePlanStore
from core_runtime.profile_workspace import validate_profile_id
from domain.tool_policy.risk import resolve_tool_risk

from .context import clean_profile_id
from .storage import AdaptiveStore


FREEZE_BLOCKED_ACTIONS = {
    "read_local",
    "local_write",
    "terminal",
    "git_write",
    "git_commit",
    "git_push",
    "git_merge",
    "browser_control",
    "computer_control",
    "external_send",
    "secrets_access",
}

_RISK_TO_ACTION = {
    "file_write": "local_write",
    "file_delete": "local_write",
    "git_write": "git_write",
    "git_commit": "git_commit",
    "git_push": "git_push",
    "git_merge": "git_merge",
    "shell": "terminal",
    "browser": "browser_control",
    "computer": "computer_control",
    "external_message": "external_send",
    "credential": "secrets_access",
}


def guard_tool_execution(
    tool_name: str,
    arguments: dict[str, Any] | None,
    context: dict[str, Any] | None,
    *,
    tool_def: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    action_id = action_for_tool(tool_name, arguments, tool_def)
    return _guard_action(action_id, arguments, context, subject_type="tool", subject_id=tool_name)


def guard_function_execution(
    function_id: str,
    arguments: dict[str, Any] | None,
    context: dict[str, Any] | None,
) -> dict[str, Any] | None:
    action_id = action_for_function(function_id)
    return _guard_action(action_id, arguments, context, subject_type="function", subject_id=function_id)


def tool_guard_response(decision: dict[str, Any], tool_name: str) -> dict[str, Any]:
    status = str(decision.get("status") or "denied")
    approval_required = status == "approval_required"
    return {
        "result": str(decision.get("message") or f"Tool '{tool_name}' blocked by adaptive runtime"),
        "is_error": not approval_required,
        "widget": {
            "type": "adaptive_policy",
            "tool_name": tool_name,
            "approval_required": approval_required,
            **decision,
        },
        "adaptive_policy": decision,
        "adaptive_guard": True,
        "approval_required": approval_required,
    }


def action_for_function(function_id: str) -> str | None:
    name = str(function_id or "").strip().lower()
    if not name or name.startswith("adaptive_"):
        return None
    if name in {"tool_file_reader", "coding_file_read"}:
        return "read_local"
    if name.startswith("coding_file_"):
        return "local_write"
    if name.startswith("coding_terminal_"):
        return "terminal"
    if name.startswith("coding_git_"):
        if name.endswith("_get") or name.endswith("_status") or name.endswith("_diff"):
            return "read_local"
        if "commit" in name:
            return "git_commit"
        if "push" in name:
            return "git_push"
        if "merge" in name:
            return "git_merge"
        return "git_write"
    if name.startswith("browser_"):
        return "browser_control"
    if name.startswith("computer_"):
        return "computer_control"
    if name in {"input_endpoint_create", "input_endpoint_delete"}:
        return "external_send"
    if name.startswith("ai_set_") or name.startswith("ai_delete_") or name.startswith("ai_rename_"):
        return "secrets_access" if "key" in name else "local_write"
    return None


def action_for_tool(
    tool_name: str,
    arguments: dict[str, Any] | None,
    tool_def: dict[str, Any] | None = None,
) -> str | None:
    name = str(tool_name or "").strip().lower()
    args = arguments if isinstance(arguments, dict) else {}
    action = str(args.get("action") or args.get("operation") or "").strip().lower()
    if name in {"browser_computer", "browser_use"}:
        if action.startswith("computer."):
            return "computer_control"
        return "browser_control"
    if name == "computer_use" or name.startswith("computer_"):
        return "computer_control"
    if name in {"external_send", "send_external"} or ("external" in name and "send" in name):
        return "external_send"
    if name in {"file_reader", "coding_file_read"} or "file_read" in name:
        return "read_local"
    if any(part in name for part in ("file_write", "write_file", "file_create", "file_patch", "file_delete")):
        return "local_write"
    if any(part in name for part in ("terminal", "shell", "exec")):
        return "terminal"
    if "git_commit" in name:
        return "git_commit"
    if "git_push" in name:
        return "git_push"
    if "git_merge" in name:
        return "git_merge"
    if any(part in name for part in ("git_write", "git_branch")):
        return "git_write"
    if "secret" in name or "credential" in name:
        return "secrets_access"

    risk = resolve_tool_risk(tool_def if isinstance(tool_def, dict) else {}, name)
    return _RISK_TO_ACTION.get(str(risk or ""))


def _guard_action(
    action_id: str | None,
    arguments: dict[str, Any] | None,
    context: dict[str, Any] | None,
    *,
    subject_type: str,
    subject_id: str,
) -> dict[str, Any] | None:
    if not action_id:
        return None
    args = arguments if isinstance(arguments, dict) else {}
    ctx = context if isinstance(context, dict) else {}

    frozen = _frozen_profile(args, ctx)
    if frozen is not None and action_id in FREEZE_BLOCKED_ACTIONS:
        profile_id, state = frozen
        return {
            "status": "denied",
            "code": "ADAPTIVE_FROZEN",
            "message": "adaptive runtime is frozen",
            "action_id": action_id,
            "subject_type": subject_type,
            "subject_id": str(subject_id or ""),
            "profile_id": profile_id,
            "reason": state.get("reason"),
        }

    profile_decision = _profile_decision(action_id, args, ctx)
    if profile_decision is not None:
        status, profile_id, level = profile_decision
        if status == "allow":
            return None
        if status == "approval_required":
            return {
                "status": "approval_required",
                "code": "ADAPTIVE_PROFILE_APPROVAL_REQUIRED",
                "message": "adaptive operating profile requires approval",
                "action_id": action_id,
                "subject_type": subject_type,
                "subject_id": str(subject_id or ""),
                "profile_id": profile_id,
                "level": level,
            }
        return {
            "status": "denied",
            "code": "ADAPTIVE_PROFILE_DENIED",
            "message": "adaptive operating profile denies this action",
            "action_id": action_id,
            "subject_type": subject_type,
            "subject_id": str(subject_id or ""),
            "profile_id": profile_id,
            "level": level,
        }

    return None


def _frozen_profile(args: dict[str, Any], ctx: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    for profile_id in _candidate_profile_ids(args, ctx):
        state = AdaptiveStore(profile_id).read_json(
            "activity/freeze_state.json",
            {"profile_id": profile_id, "frozen": False},
        )
        if isinstance(state, dict) and bool(state.get("frozen")):
            return profile_id, state
    return None


def _profile_decision(action_id: str, args: dict[str, Any], ctx: dict[str, Any]) -> tuple[str, str, str] | None:
    store = OperatingProfilePlanStore()
    for profile_id in _candidate_profile_ids(args, ctx):
        profile = store.load_active_profile(profile_id)
        if profile is None:
            continue
        level = profile.policy.level_for(action_id).value
        if level == "allow":
            return "allow", profile_id, level
        if level == "ask":
            return "approval_required", profile_id, level
        return "denied", profile_id, level
    return None


def _candidate_profile_ids(args: dict[str, Any], ctx: dict[str, Any]) -> list[str]:
    values: list[Any] = [
        ctx.get("profile_id"),
        ctx.get("active_startup_profile_id"),
        (ctx.get("active_startup_profile") or {}).get("profile_id")
        if isinstance(ctx.get("active_startup_profile"), dict)
        else None,
        (ctx.get("runtime_profile") or {}).get("profile_id")
        if isinstance(ctx.get("runtime_profile"), dict)
        else None,
    ]
    try:
        from core_runtime.profile_paths import active_profile_id

        values.append(active_profile_id())
    except Exception:
        pass
    values.extend([args.get("profile_id"), "default"])

    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        try:
            profile_id = validate_profile_id(clean_profile_id(text))
        except Exception:
            continue
        if profile_id not in result:
            result.append(profile_id)
    return result or ["default"]
