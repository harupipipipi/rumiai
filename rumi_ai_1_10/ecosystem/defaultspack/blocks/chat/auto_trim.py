import sys
import os
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from blocks._common import ok, error, gen_id, timestamp

from domain.chat.store import ChatStore
from blocks.chat.send import _ai_direct_complete


def _build_text_from_content(content):
    """content フィールドからテキスト表現を構築する。
    content が文字列ならそのまま返す。
    content がリスト（マルチモーダル）なら text パートだけ抽出して結合する。
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                btype = block.get("type", "text")
                if btype == "text":
                    parts.append(block.get("text", ""))
                elif btype == "tool_call":
                    name = block.get("name", "unknown")
                    parts.append("[tool_call: " + name + "]")
                elif btype == "tool_result":
                    tool_content = block.get("content", "")
                    if isinstance(tool_content, str):
                        parts.append(tool_content)
                    else:
                        parts.append(str(tool_content))
                else:
                    parts.append(block.get("text", str(block)))
            elif isinstance(block, str):
                parts.append(block)
            else:
                parts.append(str(block))
        return "\n".join(t for t in parts if t)
    return str(content)


def _build_analysis_prompt(messages_with_ids, max_context_tokens=None):
    """AI にトリム対象を判断させるプロンプトを構築する。"""
    system_text = (
        "You are a conversation analyst. Analyze the following conversation and identify "
        "segments of intermediate/verbose messages that can be summarized without losing "
        "important information. Focus on:\n"
        "- Intermediate work logs or step-by-step outputs that have a final summary\n"
        "- Repetitive trial-and-error messages where only the conclusion matters\n"
        "- Debug outputs or verbose logs\n"
        "- Messages that are superseded by later corrections\n\n"
        "Do NOT suggest trimming:\n"
        "- The initial user request\n"
        "- Final results or conclusions\n"
        "- Important decisions or turning points\n"
        "- Messages the user explicitly asked to keep\n\n"
    )
    if max_context_tokens is not None:
        system_text += (
            "The conversation should ideally fit within "
            + str(max_context_tokens)
            + " tokens after trimming.\n\n"
        )
    system_text += (
        "Respond with a JSON array of segments to trim. Each segment:\n"
        '{"start_id": "<message_id>", "end_id": "<message_id>", '
        '"reason": "<why this can be trimmed>", "summary_preview": "<brief preview of what the summary would say>"}\n\n'
        "If no trimming is needed, respond with an empty array: []\n"
        "Output ONLY the JSON array, nothing else."
    )

    conversation_lines = []
    for entry in messages_with_ids:
        msg_id = entry["id"]
        role = entry["role"]
        content = entry["content"]
        if not content:
            content = "(empty)"
        if isinstance(content, str) and len(content) > 200:
            content = content[:200] + "..."
        conversation_lines.append("[ID: " + msg_id + "] [" + role + "]: " + content)

    conversation_text = "\n".join(conversation_lines)

    messages = [
        {"role": "system", "content": system_text},
        {"role": "user", "content": "Analyze this conversation:\n\n" + conversation_text},
    ]
    return messages


def _parse_trim_plan(response_text):
    """AI 応答の JSON をパースして trim_plan segments を返す。"""
    text = response_text.strip()
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1:
        return []
    json_str = text[start:end + 1]
    try:
        segments = json.loads(json_str)
    except json.JSONDecodeError:
        return []
    if not isinstance(segments, list):
        return []
    valid_segments = []
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        if "start_id" not in seg or "end_id" not in seg:
            continue
        valid_segments.append({
            "start_id": str(seg["start_id"]),
            "end_id": str(seg["end_id"]),
            "reason": str(seg.get("reason", "")),
            "summary_preview": str(seg.get("summary_preview", "")),
        })
    return valid_segments


def _extract_text_from_response(response):
    """AI応答からテキストを抽出する。"""
    if isinstance(response, dict) and "data" in response:
        response = response["data"]
    content = response.get("content", [])
    if isinstance(content, str):
        return content
    parts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
        elif isinstance(block, str):
            parts.append(block)
    return "\n".join(parts)


def _unavailable_analysis_response():
    """Structured error used by legacy callers if AI analysis is unavailable."""
    return {
        "success": False,
        "error": "AI analysis is unavailable",
        "error_type": "not_implemented",
    }


def run(input_data, context):
    store = ChatStore()

    # --- バリデーション ---
    conversation_id = input_data.get("conversation_id")
    if not conversation_id:
        return error("conversation_id is required", "INVALID_INPUT")

    conv = store.get_conversation(conversation_id)
    if conv is None:
        return error("Conversation not found", "NOT_FOUND")

    messages = conv.get("messages", [])
    if not messages:
        return ok({"trim_plan": {"segments": []}, "message": "No messages to analyze"})

    # --- メッセージ ID 付きリストを元の messages から直接構築 ---
    # convert_to_standard は 1:N 変換するため使わない（インデックスずれ防止）
    messages_with_ids = []
    for msg in messages:
        msg_id = msg.get("id") or gen_id()
        role = msg.get("role", "unknown")
        content_text = _build_text_from_content(msg.get("content", ""))
        messages_with_ids.append({
            "id": msg_id,
            "role": role,
            "content": content_text,
        })

    # --- AI に分析させる ---
    model = input_data.get("model", "default")
    if model == "default":
        model = conv.get("model", "stub/default")
    max_context_tokens = input_data.get("max_context_tokens")
    analysis_messages = _build_analysis_prompt(messages_with_ids, max_context_tokens)

    call_handler = context.get("call_handler") if context else None
    if call_handler is not None:
        try:
            ai_params = {
                "model": model,
                "messages": analysis_messages,
                "tools": [],
                "params": {},
            }
            response = call_handler("defaults.ai.complete", ai_params)
        except Exception as exc:
            return error("AI request failed: " + str(exc), "AI_ERROR")
        if isinstance(response, dict) and response.get("status") == "error":
            err = response.get("error", {})
            message = err.get("message") if isinstance(err, dict) else None
            return error(str(message or "AI request failed"), "AI_ERROR")
        if isinstance(response, dict) and response.get("status") == "ok":
            response = response.get("data", {})
    else:
        response, ai_error = _ai_direct_complete(model, analysis_messages, [], {})
        if ai_error is not None:
            return error(ai_error, "AI_ERROR")
    if not isinstance(response, dict):
        return error("AI provider returned an invalid response", "AI_ERROR")

    response_text = _extract_text_from_response(response)
    segments = _parse_trim_plan(response_text)

    # --- segments のバリデーション（存在するメッセージIDか確認） ---
    msg_id_set = {m["id"] for m in messages}
    validated_segments = []
    for seg in segments:
        if seg["start_id"] in msg_id_set and seg["end_id"] in msg_id_set:
            validated_segments.append(seg)

    return ok({
        "trim_plan": {
            "segments": validated_segments,
        },
        "conversation_id": conversation_id,
        "total_messages": len(messages),
    })
