import time
import uuid


def _gen_id():
    return str(uuid.uuid4())


def _now_ms():
    return int(time.time() * 1000)


def build_assistant_message(conversation_id, parent_id, sequence_number, response, model):
    """AI応答の StandardResponse から完全な RumiMessage を構築する。

    response は {"content": list, "finish_reason": str, "usage": dict} 形式。
    """
    content = response.get("content", [])
    if isinstance(content, str):
        content = [{"type": "text", "text": content}]
    raw_parts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            raw_parts.append(block.get("text", ""))
        elif isinstance(block, str):
            raw_parts.append(block)
    raw_text = " ".join(raw_parts)
    msg = {
        "id": _gen_id(),
        "conversation_id": conversation_id,
        "parent_id": parent_id,
        "children_ids": [],
        "sequence_number": sequence_number,
        "role": "assistant",
        "content": content,
        "raw_text": raw_text,
        "created_at": _now_ms(),
        "finish_reason": response.get("finish_reason", "stop"),
        "usage": response.get("usage", {}),
        "widget": None,
        "metadata": response.get("metadata", {}),
        "events": response.get("events", []),
        "tool_logs": response.get("tool_logs", []),
        "model": model,
    }
    return msg
