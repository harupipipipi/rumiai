from __future__ import annotations

from typing import Any


ASSISTANT_PROGRESS_TOOL_NAME = "assistant_progress"
ASSISTANT_PROGRESS_DISPLAY_NAME = "作業状況"
ASSISTANT_PROGRESS_MAX_UPDATES = 6
ASSISTANT_PROGRESS_MAX_RELATED_TOOL_IDS = 4
ASSISTANT_PROGRESS_TEXT_LIMIT = 120
ASSISTANT_PROGRESS_PHASES = {"inspect", "change", "verify", "recover", "finalize"}
ASSISTANT_PROGRESS_STATUSES = {"active", "completed", "blocked"}


def assistant_progress_provider_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": ASSISTANT_PROGRESS_TOOL_NAME,
            "description": (
                "Emit a brief user-visible work progress update. "
                "Use sparingly at phase changes, important findings, failures, or final verification."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "phase": {
                        "type": "string",
                        "enum": sorted(ASSISTANT_PROGRESS_PHASES),
                        "description": "Current work phase.",
                    },
                    "status": {
                        "type": "string",
                        "enum": sorted(ASSISTANT_PROGRESS_STATUSES),
                        "description": "Progress status.",
                    },
                    "summary": {
                        "type": "string",
                        "maxLength": ASSISTANT_PROGRESS_TEXT_LIMIT,
                        "description": "Short user-visible summary of observable work.",
                    },
                    "next_action": {
                        "type": "string",
                        "maxLength": ASSISTANT_PROGRESS_TEXT_LIMIT,
                        "description": "Concrete next action shown to the user.",
                    },
                    "related_tool_call_ids": {
                        "type": "array",
                        "maxItems": ASSISTANT_PROGRESS_MAX_RELATED_TOOL_IDS,
                        "items": {"type": "string"},
                        "description": "Optional related external tool call ids.",
                    },
                },
                "required": ["phase", "status", "summary", "next_action"],
            },
        },
        "metadata": {
            "internal_control_tool": True,
            "display_name": ASSISTANT_PROGRESS_DISPLAY_NAME,
            "exclude_from_tool_hub": True,
            "exclude_from_tool_limits": True,
        },
    }


def assistant_progress_system_instruction() -> str:
    return (
        "Internal progress tool: assistant_progress is only for short user-visible status, not reasoning. "
        "Call it at most at phase changes, important discoveries, failures, or final verification. "
        "Do not call it before every tool. Do not include hidden reasoning, analysis, or chain-of-thought. "
        "Keep summary and next_action under 120 characters. "
        "A normal external tool should occur between repeated progress updates unless you are finalizing or blocked."
    )


def with_assistant_progress_tool(provider_tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not provider_tools:
        return []
    if any(tool_name(tool) == ASSISTANT_PROGRESS_TOOL_NAME for tool in provider_tools):
        return list(provider_tools)
    return [*provider_tools, assistant_progress_provider_tool()]


def tool_name(tool: Any) -> str:
    if not isinstance(tool, dict):
        return ""
    function_def = tool.get("function")
    if isinstance(function_def, dict) and function_def.get("name"):
        return str(function_def.get("name") or "").strip()
    return str(tool.get("tool_id") or tool.get("name") or "").strip()


def is_assistant_progress_tool_name(name: str) -> bool:
    return str(name or "").strip() == ASSISTANT_PROGRESS_TOOL_NAME


def clamp_text(value: Any, limit: int = ASSISTANT_PROGRESS_TEXT_LIMIT) -> str:
    text = str(value or "").strip()
    return text[:limit]


def normalize_assistant_progress_payload(arguments: dict[str, Any] | None) -> tuple[dict[str, Any], list[str]]:
    args = arguments if isinstance(arguments, dict) else {}
    errors: list[str] = []
    phase = str(args.get("phase") or "inspect").strip().lower()
    if phase not in ASSISTANT_PROGRESS_PHASES:
        errors.append("invalid_phase")
        phase = "inspect"
    status = str(args.get("status") or "active").strip().lower()
    if status not in ASSISTANT_PROGRESS_STATUSES:
        errors.append("invalid_status")
        status = "active"
    summary = clamp_text(args.get("summary"))
    next_action = clamp_text(args.get("next_action") or args.get("nextAction"))
    if not summary:
        errors.append("missing_summary")
        summary = "作業状況を更新しました"
    if not next_action:
        errors.append("missing_next_action")
        next_action = "次の確認を続けます"
    related_raw = args.get("related_tool_call_ids")
    related = [
        str(item or "").strip()
        for item in (related_raw if isinstance(related_raw, list) else [])
        if str(item or "").strip()
    ][:ASSISTANT_PROGRESS_MAX_RELATED_TOOL_IDS]
    return {
        "phase": phase,
        "status": status,
        "summary": summary,
        "next_action": next_action,
        "related_tool_call_ids": related,
    }, errors
