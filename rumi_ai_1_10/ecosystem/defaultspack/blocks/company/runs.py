from typing import Any

from blocks._common import ok, error
from domain.company.runtime_store import CompanyRuntimeStore

from ._helpers import company_id_from, invalid, limit_offset, require_dict


def run(input_data, context):
    if require_dict(input_data) is None:
        return invalid("input_data must be a dict")
    company_id = company_id_from(input_data)
    if not company_id:
        return invalid("company_id is required")
    try:
        limit, offset = limit_offset(input_data)
        runs, total = CompanyRuntimeStore().list_run_links(
            company_id,
            agent_id=input_data.get("agent_id"),
            task_id=input_data.get("task_id"),
            status=input_data.get("status"),
            limit=limit,
            offset=offset,
            include_total=True,
        )
        return ok({"runs": [_with_agent_run_preview(run) for run in runs], "total": total})
    except Exception as exc:
        return error("company runs failed: " + str(exc), "COMPANY_RUNS_ERROR")


def _with_agent_run_preview(run: dict) -> dict:
    run_id = str(run.get("run_id") or "").strip()
    if not run_id:
        return run
    try:
        from domain.agent_runtime.run_store import AgentRunStore

        run_store = AgentRunStore()
        agent_run = run_store.get_run(run_id)
        messages = run_store.list_messages(run_id, limit=12)
    except Exception:
        agent_run = None
        messages = []
    if not isinstance(agent_run, dict):
        return run
    preview = _result_preview(agent_run.get("result_json"))
    enriched = dict(run)
    enriched["agent_run"] = {
        "status": agent_run.get("status"),
        "model": agent_run.get("model"),
        "result_preview": preview,
        "error": agent_run.get("error"),
        "conversation": _conversation_tail(agent_run, messages, preview),
        "updated_at": agent_run.get("updated_at"),
    }
    return enriched


def _conversation_tail(agent_run: dict[str, Any], messages: list[dict[str, Any]], result_preview: str) -> list[dict[str, Any]]:
    conversation: list[dict[str, Any]] = []
    for message in messages:
        payload = message.get("content_json")
        role = str(message.get("role") or (payload.get("role") if isinstance(payload, dict) else "") or "").strip()
        if not role or role == "system":
            continue
        content = _message_text(payload).strip()
        if not content:
            continue
        conversation.append(
            {
                "role": role,
                "label": _conversation_label(role),
                "content": _clip_text(content, 900),
            }
        )
    if not any(item.get("role") == "user" for item in conversation):
        task_text = str(agent_run.get("task") or "").strip()
        if task_text:
            conversation.insert(
                0,
                {
                    "role": "user",
                    "label": "Assignment",
                    "content": _clip_text(task_text, 900),
                },
            )
    error_text = str(agent_run.get("error") or "").strip()
    if error_text:
        conversation.append(
            {
                "role": "error",
                "label": "Agent error",
                "content": _clip_text(error_text, 900),
                "is_error": True,
            }
        )
    elif result_preview and not _has_assistant_text(conversation, result_preview):
        conversation.append(
            {
                "role": "assistant",
                "label": "Agent reply",
                "content": _clip_text(result_preview, 900),
            }
        )
    return conversation[-6:]


def _conversation_label(role: str) -> str:
    labels = {
        "user": "Assignment",
        "assistant": "Agent reply",
        "tool": "Tool result",
        "function": "Tool result",
        "error": "Agent error",
    }
    return labels.get(role, role.replace("_", " ").title())


def _message_text(value) -> str:
    if isinstance(value, dict) and "content" in value:
        return _result_text(value.get("content"))
    return _result_text(value)


def _has_assistant_text(conversation: list[dict[str, Any]], text: str) -> bool:
    clean = text.strip()
    if not clean:
        return False
    return any(item.get("role") == "assistant" and clean in str(item.get("content") or "") for item in conversation)


def _clip_text(text: str, limit: int) -> str:
    clean = " ".join(text.split()) if len(text) > limit else text
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3].rstrip() + "..."


def _result_preview(value) -> str:
    text = _result_text(value).strip()
    if len(text) <= 240:
        return text
    return text[:237].rstrip() + "..."


def _result_text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                if item.get("type") == "thinking" or item.get("thinking"):
                    continue
                parts.append(str(item.get("text") or item.get("content") or ""))
            elif item is not None:
                parts.append(str(item))
        return "\n".join(part for part in parts if part)
    if isinstance(value, dict):
        for key in ("text", "content", "result", "assistant_text", "message"):
            if value.get(key):
                return _result_text(value.get(key))
    return ""
