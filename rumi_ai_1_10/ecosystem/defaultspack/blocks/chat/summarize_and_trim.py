import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from blocks._common import ok, error, gen_id, timestamp

from domain.chat.store import ChatStore
from domain.chat.message_converter import convert_to_standard
from blocks.chat.send import _ai_direct_complete


def _extract_text_from_response(response):
    """AI応答からテキストを抽出する。call_handler が ok ラッパー付き/なし両対応。"""
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


def _build_summarize_prompt(standard_messages, instruction=None):
    """要約用のシステムプロンプトとメッセージリストを構築する。"""
    system_text = (
        "You are a conversation summarizer. "
        "The user will provide a segment of conversation messages. "
        "Summarize the key information, decisions, and results from these messages. "
        "Be concise but preserve all important details, outcomes, and conclusions. "
        "Output ONLY the summary text, no extra formatting."
    )
    if instruction:
        system_text += "\n\nAdditional instruction: " + instruction

    conversation_text_parts = []
    for msg in standard_messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if content:
            conversation_text_parts.append("[" + role + "]: " + content)

    conversation_text = "\n".join(conversation_text_parts)

    messages = [
        {"role": "system", "content": system_text},
        {"role": "user", "content": "Please summarize the following conversation segment:\n\n" + conversation_text},
    ]
    return messages


def _unavailable_summary_response(standard_messages):
    """Structured error used by legacy callers if AI summarization is unavailable."""
    return {
        "success": False,
        "error": "AI summarization is unavailable",
        "error_type": "not_implemented",
    }


def run(input_data, context):
    store = ChatStore()

    # --- バリデーション ---
    conversation_id = input_data.get("conversation_id")
    if not conversation_id:
        return error("conversation_id is required", "INVALID_INPUT")

    start_message_id = input_data.get("start_message_id")
    if not start_message_id:
        return error("start_message_id is required", "INVALID_INPUT")

    end_message_id = input_data.get("end_message_id")
    if not end_message_id:
        return error("end_message_id is required", "INVALID_INPUT")

    conv = store.get_conversation(conversation_id)
    if conv is None:
        return error("Conversation not found", "NOT_FOUND")

    # --- 範囲取得 ---
    range_result = store.get_messages_range(conversation_id, start_message_id, end_message_id)
    if range_result is None:
        return error("Invalid message range: start or end message not found", "INVALID_RANGE")

    range_messages, start_idx = range_result
    if not range_messages:
        return error("No messages in specified range", "EMPTY_RANGE")

    if len(range_messages) < 2:
        return error("At least 2 messages required for summarization", "RANGE_TOO_SMALL")

    original_message_ids = [m["id"] for m in range_messages]

    # --- AI に要約させる ---
    standard_messages = convert_to_standard(range_messages)
    model = input_data.get("model", "default")
    if model == "default":
        model = conv.get("model", "stub/default")
    instruction = input_data.get("instruction")
    summarize_messages = _build_summarize_prompt(standard_messages, instruction)

    call_handler = context.get("call_handler") if context else None
    if call_handler is not None:
        try:
            ai_params = {
                "model": model,
                "messages": summarize_messages,
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
        response, ai_error = _ai_direct_complete(model, summarize_messages, [], {})
        if ai_error is not None:
            return error(ai_error, "AI_ERROR")
    if not isinstance(response, dict):
        return error("AI provider returned an invalid response", "AI_ERROR")

    summary_text = _extract_text_from_response(response)

    # --- 範囲内メッセージを一括削除 ---
    first_msg = range_messages[0]
    parent_of_range = first_msg.get("parent_id")

    last_msg = range_messages[-1]
    delete_id_set = set(original_message_ids)
    surviving_children = [cid for cid in last_msg.get("children_ids", []) if cid not in delete_id_set]

    store.delete_messages_bulk(conversation_id, original_message_ids)

    # --- 要約メッセージを挿入 ---
    summary_msg_dict = {
        "role": "assistant",
        "content": [{"type": "text", "text": summary_text}],
        "metadata": {
            "is_summary": True,
            "original_message_ids": original_message_ids,
            "summary_instruction": instruction,
        },
    }
    summary_msg = store.insert_message_at(
        conversation_id, summary_msg_dict, start_idx,
        parent_id=parent_of_range,
        children_ids=surviving_children,
    )
    if summary_msg is None:
        return error("Failed to insert summary message", "INTERNAL_ERROR")

    # --- 更新後の会話を返す ---
    updated_conv = store.get_conversation(conversation_id)
    return ok({
        "conversation": updated_conv,
        "summary_message": summary_msg,
        "deleted_message_ids": original_message_ids,
    })
