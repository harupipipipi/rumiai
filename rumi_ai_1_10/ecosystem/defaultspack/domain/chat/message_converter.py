from domain.chat.ir_legacy_adapter import ir_to_legacy_standard_messages, stored_messages_to_ir


def convert_to_standard(rumi_messages):
    """RumiMessage のリストを StandardMessage のリストに変換する。

    Compatibility API. The public output remains the legacy StandardMessage
    shape, but the conversion now passes through Rumi Chat IR v2 so newer
    provider paths share one canonical adapter.
    """
    conversation_id = ""
    for message in rumi_messages or []:
        if isinstance(message, dict) and message.get("conversation_id"):
            conversation_id = str(message.get("conversation_id") or "")
            break
    return ir_to_legacy_standard_messages(stored_messages_to_ir(conversation_id, list(rumi_messages or [])))
