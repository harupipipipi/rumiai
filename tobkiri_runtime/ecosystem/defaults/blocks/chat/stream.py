import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from blocks._common import ok, error, gen_id, timestamp

from domain.ai_client.client import AIClient
from domain.chat.store import ChatStore
from domain.chat.message_converter import convert_to_standard
from domain.chat.message_builder import build_assistant_message
from domain.prompt.manager import get_manager
from blocks.chat._context_helpers import extract_user_text, enrich_messages


def _has_real_provider(client, model):
    """model に対応する実プロバイダーが登録されているか判定する。
    stub プロバイダーに解決される場合は False を返す。
    ただし model が 'stub/' で始まる場合は意図的な stub 利用とみなし True を返す。"""
    if model.startswith("stub/"):
        return True
    provider, _ = client.resolve_provider(model)
    from domain.ai_client.providers.stub_provider import StubProvider
    return not isinstance(provider, StubProvider)


def _consume_stream(stream_result):
    """ストリームチャンクを全て消費し、StandardResponse 形式の dict を返す。

    stream_result はジェネレータまたはリスト。各チャンクは:
      {"type": "content_delta", "delta": {"type": "text", "text": "..."}}
      {"type": "stream_end", "finish_reason": "...", "usage": {...}}
    """
    text_parts = []
    finish_reason = "stop"
    usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    for chunk in stream_result:
        chunk_type = chunk.get("type", "")
        if chunk_type == "content_delta":
            delta = chunk.get("delta", {})
            delta_text = delta.get("text", "")
            if delta_text:
                text_parts.append(delta_text)
        elif chunk_type == "stream_end":
            finish_reason = chunk.get("finish_reason", "stop")
            usage = chunk.get("usage", usage)

    full_text = "".join(text_parts)
    return {
        "content": [{"type": "text", "text": full_text}],
        "finish_reason": finish_reason,
        "usage": usage,
    }


def _ai_direct_stream(model, messages):
    """AIClient を直接呼び出してストリーム応答を取得し、集約した StandardResponse を返す。

    Returns:
        (response_dict, None) on success
        (None, error_message) on failure
    """
    try:
        client = AIClient()
        if not _has_real_provider(client, model):
            return None, "AI provider API key not configured"
        stream_result = client.stream(model, messages)
        response = _consume_stream(stream_result)
        return response, None
    except RuntimeError as exc:
        return None, "AI request failed: " + str(exc)
    except Exception as exc:
        return None, "AI request failed: " + str(exc)


def run(input_data, context):
    store = ChatStore()
    conversation_id = input_data.get("conversation_id")
    if not conversation_id:
        return error("conversation_id is required", "INVALID_INPUT")
    conv = store.get_conversation(conversation_id)
    if conv is None:
        return error("Conversation not found", "NOT_FOUND")
    message = input_data.get("message")
    if not message or not isinstance(message, dict):
        return error("message dict is required", "INVALID_INPUT")

    # --- 空メッセージ検証 ---
    raw_content = message.get("content")
    if raw_content is None or raw_content == "":
        return error("message content must not be empty", "INVALID_INPUT")
    if isinstance(raw_content, list) and len(raw_content) == 0:
        return error("message content must not be empty", "INVALID_INPUT")

    role = message.get("role", "user")
    content = message.get("content", [])
    if isinstance(content, str):
        content = [{"type": "text", "text": content}]
    user_msg_dict = {
        "role": role,
        "content": content,
    }
    user_msg = store.add_message(conversation_id, user_msg_dict)
    if user_msg is None:
        return error("Failed to add user message", "INTERNAL_ERROR")
    chain = store.get_message_chain(conversation_id, user_msg["id"])
    standard_messages = convert_to_standard(chain)
    model = conv.get("model", "stub/default")

    # --- 9b: ナレッジ / メモリ自動検索 & コンテキスト変数実動化 ---
    manager = get_manager()
    system_prompt = manager.get_system_prompt()
    user_text = extract_user_text(content)
    try:
        enrich_messages(
            standard_messages, system_prompt, conversation_id, user_text, manager,
        )
    except Exception:
        # 補強処理全体が失敗してもフローを止めない
        # fallback: system prompt を standard_messages に挿入
        if system_prompt:
            standard_messages.insert(0, {"role": "system", "content": system_prompt})

    # 防御ガード: enrich_messages が部分的に失敗し system メッセージ未挿入の場合を補完
    if system_prompt and (
        not standard_messages or standard_messages[0].get("role") != "system"
    ):
        standard_messages.insert(0, {"role": "system", "content": system_prompt})

    call_handler = context.get("call_handler") if context else None
    stream_id = gen_id()
    if call_handler is not None:
        try:
            ai_params = {
                "model": model,
                "messages": standard_messages,
                "tools": [],
                "params": {},
            }
            result = call_handler("defaults.ai.stream", ai_params)
            if isinstance(result, dict) and "stream_id" in result:
                stream_id = result["stream_id"]
        except Exception:
            pass
        return ok({"stream_id": stream_id, "conversation_id": conversation_id})
    else:
        # フォールバック: AIClient を直接呼び出しストリームを集約する
        response, ai_error = _ai_direct_stream(model, standard_messages)
        if ai_error is not None:
            return error(ai_error, "AI_ERROR")

        # ストリーム集約完了 — アシスタントメッセージを保存
        seq = user_msg.get("sequence_number", 1) + 1
        assistant_msg_dict = build_assistant_message(
            conversation_id=conversation_id,
            parent_id=user_msg["id"],
            sequence_number=seq,
            response=response,
            model=model,
        )
        assistant_msg = store.add_message(conversation_id, assistant_msg_dict)
        if assistant_msg is None:
            return error("Failed to add assistant message", "INTERNAL_ERROR")
        return ok({
            "stream_id": stream_id,
            "conversation_id": conversation_id,
            "message": assistant_msg,
        })
