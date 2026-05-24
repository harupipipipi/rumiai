from __future__ import annotations

from domain.chat.steer import ConversationSteerStore
from domain.input.envelope import RumiInputEnvelope


def handle(envelope: RumiInputEnvelope, context: dict[str, Any] | None = None) -> dict[str, Any]:
    instruction = str(
        envelope.input
        or envelope.params.get("instruction")
        or envelope.params.get("prompt")
        or envelope.params.get("message")
        or ""
    ).strip()
    if not instruction:
        return {"status": "error", "code": "MISSING_INPUT", "error": "interrupt instruction is required", "assistant_text": ""}
    target = envelope.target if isinstance(envelope.target, dict) else {}
    execution_id = str(target.get("execution_id") or target.get("agent_run_id") or "").strip()
    if execution_id:
        from blocks.agent.interrupt.add import run as add_interrupt

        result = add_interrupt(
            {
                "execution_id": execution_id,
                "instruction": instruction,
                "priority": str(envelope.delivery.get("priority") or envelope.params.get("priority") or "high"),
            },
            context or {},
        )
        if isinstance(result, dict) and result.get("status") == "ok":
            data = result.get("data") if isinstance(result.get("data"), dict) else {}
            return {"status": "ok", "assistant_text": "", "interrupt": data}
        error_data = result.get("error") if isinstance(result, dict) and isinstance(result.get("error"), dict) else {}
        return {
            "status": "error",
            "assistant_text": "",
            "code": str(error_data.get("code") or "INPUT_ACTION_FAILED"),
            "error": str(error_data.get("message") or "interrupt failed"),
        }

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
                "source": "input_action.run_interrupt",
                "interrupt": {
                    "type": str(envelope.delivery.get("interrupt_type") or "instruction"),
                    "extensions": ["pause", "cancel", "redirect", "replace_goal"],
                },
            },
        }
    )
    return {"status": "ok", "assistant_text": "", "interrupt": item}
