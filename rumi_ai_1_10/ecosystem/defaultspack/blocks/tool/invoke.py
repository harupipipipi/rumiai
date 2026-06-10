import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from _common import error, ok  # noqa: E402
from domain.tool.permission_checker import PermissionChecker  # noqa: E402
from domain.tool.executor import ToolExecutor  # noqa: E402
from domain.tool.registry import ToolRegistry  # noqa: E402
from domain.tool_policy.internal_context import (
    internal_tool_decision,
    sanitize_tool_context,
    seal_tool_context,
)  # noqa: E402


def _is_cancelled(context):
    checker = context.get("is_cancelled") if isinstance(context, dict) else None
    if callable(checker):
        try:
            return bool(checker())
        except Exception:
            return False
    return False


def _effective_tool_allowlist(context):
    if not isinstance(context, dict):
        return set()
    value = context.get("effective_tool_allowlist")
    if not value:
        policy = context.get("profile_policy") if isinstance(context.get("profile_policy"), dict) else {}
        value = policy.get("tool_allowlist") or policy.get("enabled_tools") or policy.get("allowed_tools")
    if isinstance(value, str):
        value = [part.strip() for part in value.split(",")]
    if not isinstance(value, list):
        return set()
    return {str(item).strip() for item in value if str(item).strip()}


def _blocked_by_profile_error(tool_name, context):
    profile_id = ""
    if isinstance(context, dict):
        profile_id = str(context.get("active_startup_profile_id") or context.get("profile_id") or "")
    if profile_id:
        try:
            from core_runtime.ai_input_trace_store import AiInputTraceStore

            AiInputTraceStore().append_blocked_event(
                profile_id,
                {
                    "event": "tool_blocked",
                    "tool_id": tool_name,
                    "reason": "not_in_effective_tool_allowlist",
                    "source": "defaultspack.blocks.tool.invoke",
                },
            )
        except Exception:
            pass
    return {
        "status": "error",
        "error": {
            "code": "blocked_by_profile",
            "message": "Tool blocked by active profile",
            "details": {
                "tool_id": tool_name,
                "profile_id": profile_id,
                "reason": "not_in_effective_tool_allowlist",
            },
        },
    }


CLIENT_CONTEXT_DENY_KEYS = {
    "artifact_root",
    "workspace_root",
    "workspaceRoot",
    "rootPath",
    "profile_policy",
    "active_startup_profile_id",
    "profile_id",
    "effective_tool_allowlist",
}


def _sanitize_payload_context(payload_context):
    if not isinstance(payload_context, dict):
        return {}
    clean = sanitize_tool_context(payload_context)
    for key in CLIENT_CONTEXT_DENY_KEYS:
        clean.pop(key, None)
    return clean


def run(input_data, context):
    """defaults.tool.invoke — ツールを実行する"""
    context = context if isinstance(context, dict) else {}
    payload_context = _sanitize_payload_context(input_data.get("context"))
    if payload_context:
        context = {**context, **payload_context}
    tool_name = input_data.get("tool_name")
    if not tool_name:
        return error("tool_name is required", "MISSING_PARAM")
    if _is_cancelled(context):
        return error("Tool execution cancelled", "CANCELLED")

    arguments = input_data.get("arguments")
    if arguments is None:
        return error("arguments is required", "MISSING_PARAM")

    registry = ToolRegistry()
    tool_def = registry.get(tool_name)
    if tool_def is None:
        for item in registry.list_tools():
            if item.get("name") == tool_name:
                tool_def = item
                tool_name = item.get("tool_id", tool_name)
                break

    allowlist = _effective_tool_allowlist(context)
    if allowlist and tool_name not in allowlist:
        return _blocked_by_profile_error(tool_name, context)

    sealed_decision = internal_tool_decision(context)
    clean_context = sanitize_tool_context(context)
    if sealed_decision is not None:
        decision = sealed_decision
    else:
        checker = PermissionChecker(registry=registry)
        decision = checker.decide(tool_name, context=clean_context, arguments=arguments, tool_def=tool_def)
    if not decision.get("allowed", False):
        return {
            "status": "error",
            "error": {
                "code": "PERMISSION_DENIED",
                "message": "Permission denied for tool: {}".format(tool_name),
                "details": {
                    "action": decision.get("action"),
                    "matched_by": decision.get("matched_by"),
                    "matched_value": decision.get("matched_value"),
                    "reason": decision.get("reason"),
                },
            },
        }

    executor_context = seal_tool_context(clean_context, decision)
    executor = ToolExecutor()
    try:
        if _is_cancelled(executor_context):
            return error("Tool execution cancelled", "CANCELLED")
        result = executor.execute(tool_name, arguments, executor_context)
    except Exception as exc:
        return error("Tool execution failed: {}".format(exc), "EXEC_ERROR")
    if result.get("cancelled"):
        return error("Tool execution cancelled", "CANCELLED")

    return ok({
        "result": result.get("result", ""),
        "is_error": result.get("is_error", False),
        "widget": result.get("widget"),
        "tool_name": tool_name,
        **(
            {
                "status": result.get("status"),
                "code": result.get("code"),
                "reason_code": result.get("reason_code"),
                "reason": result.get("reason"),
                "required": result.get("required"),
                "actual": result.get("actual"),
                "repair_suggestions": result.get("repair_suggestions"),
            }
            if result.get("status") == "rejected"
            else {}
        ),
        "permission": {
            "action": decision.get("action", "allow"),
            "allowed": decision.get("allowed", False),
            "matched_by": decision.get("matched_by"),
            "matched_value": decision.get("matched_value"),
        },
    })
