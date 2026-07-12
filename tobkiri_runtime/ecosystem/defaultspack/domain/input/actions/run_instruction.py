from __future__ import annotations

from typing import Any

from domain.chat.steer import ConversationSteerStore
from domain.input.envelope import RumiInputEnvelope


def handle(envelope: RumiInputEnvelope, context: dict[str, Any] | None = None) -> dict[str, Any]:
    instruction = _instruction_text(envelope)
    if not instruction:
        return {"status": "error", "code": "MISSING_INPUT", "error": "instruction is required", "assistant_text": ""}
    target = envelope.target if isinstance(envelope.target, dict) else {}
    execution_id = str(target.get("execution_id") or target.get("agent_run_id") or "").strip()
    if execution_id:
        from blocks.agent.add_instruction import run as add_instruction

        result = add_instruction(
            {
                "execution_id": execution_id,
                "instruction": instruction,
                "priority": str(envelope.delivery.get("priority") or envelope.params.get("priority") or "normal"),
            },
            context or {},
        )
        return _normalize_block_result(result, execution_id=execution_id)

    conversation_id = str(
        target.get("conversation_id")
        or envelope.chat.get("conversation_id")
        or envelope.chat.get("external_key")
        or ""
    ).strip()
    item = ConversationSteerStore().enqueue(
        {
            "prompt": instruction,
            "target_type": str(target.get("target_type") or "conversation"),
            "target_id": str(target.get("target_id") or conversation_id),
            "conversation_id": conversation_id,
            "visible": envelope.delivery.get("visible", True),
            "auto_send": envelope.delivery.get("auto_send", True),
            "metadata": {
                **(envelope.metadata if isinstance(envelope.metadata, dict) else {}),
                "source": "input_action.run_instruction",
            },
        }
    )
    return {"status": "ok", "assistant_text": "", "instruction": item}


def _instruction_text(envelope: RumiInputEnvelope) -> str:
    return str(
        envelope.input
        or envelope.params.get("instruction")
        or envelope.params.get("prompt")
        or envelope.params.get("message")
        or ""
    ).strip()


def _normalize_block_result(result: Any, **extra: Any) -> dict[str, Any]:
    if isinstance(result, dict) and result.get("status") == "ok":
        return {"status": "ok", "assistant_text": "", **extra, **(result.get("data") if isinstance(result.get("data"), dict) else {})}
    if isinstance(result, dict) and result.get("error"):
        error_data = result.get("error") if isinstance(result.get("error"), dict) else {"message": str(result.get("error"))}
        return {
            "status": "error",
            "assistant_text": "",
            "code": str(error_data.get("code") or "INPUT_ACTION_FAILED"),
            "error": str(error_data.get("message") or "input action failed"),
            **extra,
        }
    return {"status": "error", "assistant_text": "", "code": "INPUT_ACTION_FAILED", "error": str(result), **extra}
