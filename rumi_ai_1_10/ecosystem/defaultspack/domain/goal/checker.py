from __future__ import annotations

import json
from typing import Any

from domain.ai_client.model_call import call_model
from domain.chat.exporter import export_json
from domain.chat.store import ChatStore
from domain.goal.store import GoalStore


CHECKER_SYSTEM_PROMPT = (
    "You are an isolated Rumi goal checker. You can only inspect exported chat "
    "JSON and summarize whether the user's objective is achieved. You cannot "
    "message or instruct the main assistant. Reply with strict JSON only."
)

CHECKER_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["running", "achieved", "failed", "blocked"]},
        "achieved": {"type": "boolean"},
        "reason": {"type": "string"},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "next_check": {"type": "string"},
    },
    "required": ["status", "reason"],
}


def run_goal_checker(
    goal_run_id: str,
    *,
    message_id: str | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    store = GoalStore()
    run = store.get_run(goal_run_id)
    if run is None:
        return {"status": "error", "code": "GOAL_RUN_NOT_FOUND", "message": "goal run not found"}
    conversation = ChatStore().get_conversation(str(run.get("conversation_id") or ""))
    if conversation is None:
        return {"status": "error", "code": "CONVERSATION_NOT_FOUND", "message": "conversation not found"}

    store.mark_check_started(str(run.get("goal_run_id") or goal_run_id), message_id=message_id)
    prompt = _checker_prompt(run, conversation)
    checker_context = _isolated_context(context or {})
    response = call_model(
        {
            "messages": [
                {"role": "system", "content": CHECKER_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 700,
            "thinking_level": "none",
            "output_schema": CHECKER_SCHEMA,
        },
        checker_context,
        call_handler=checker_context.get("call_handler"),
    )
    if not isinstance(response, dict) or response.get("status") == "error":
        message = str((response or {}).get("error") or "goal checker failed")
        store.record_check_error(goal_run_id, message, message_id=message_id)
        return {"status": "error", "code": "CHECKER_FAILED", "message": message}

    verdict = _parse_verdict(response.get("output"))
    updated = store.apply_checker_verdict(
        goal_run_id,
        verdict,
        message_id=message_id,
        internal=True,
    )
    return {"status": "ok", "data": {"run": updated, "verdict": updated.get("latest_verdict")}}


def _checker_prompt(run: dict[str, Any], conversation: dict[str, Any]) -> str:
    objective = str(run.get("objective") or "").strip()
    exported = export_json(_redacted_conversation(conversation))
    return (
        f"Objective:\n{objective}\n\n"
        "Exported chat JSON follows. Decide whether the objective is achieved "
        "based only on visible persisted conversation and artifact summaries.\n\n"
        f"{exported}"
    )


def _redacted_conversation(conversation: dict[str, Any]) -> dict[str, Any]:
    clone = json.loads(json.dumps(conversation, ensure_ascii=False, default=str))
    for message in clone.get("messages", []) if isinstance(clone.get("messages"), list) else []:
        if not isinstance(message, dict):
            continue
        message.pop("hidden_context", None)
        message.pop("scratch", None)
        metadata = message.get("metadata")
        if isinstance(metadata, dict):
            metadata.pop("hidden_context", None)
            metadata.pop("scratch", None)
    return clone


def _isolated_context(context: dict[str, Any]) -> dict[str, Any]:
    isolated: dict[str, Any] = {}
    if callable(context.get("call_handler")):
        isolated["call_handler"] = context.get("call_handler")
    for key in ("request_id", "conversation_id", "user_id"):
        if key in context:
            isolated[key] = context[key]
    isolated["_goal_checker_isolated"] = True
    return isolated


def _parse_verdict(output: Any) -> dict[str, Any]:
    if isinstance(output, dict):
        return output
    text = str(output or "").strip()
    if text.startswith("```"):
        text = "\n".join(line for line in text.splitlines() if not line.strip().startswith("```")).strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    return {
        "status": "running",
        "achieved": False,
        "reason": "checker returned an unparsable verdict",
        "evidence": [],
    }
