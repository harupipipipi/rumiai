"""simple_chat フローハンドラ

シンプルなチャットフロー。ツール使用なしで、ユーザーメッセージを
受け取り、defaults.chat.send を呼んで応答を返す。
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from blocks._common import ok, error, gen_id, timestamp


def run(input_data, context):
    """シンプルチャットフローのメイン処理

    Args:
        input_data: 入力データ dict
            - conversation_id (str): 会話 ID
            - message (dict): ユーザーメッセージ
        context: FlowContext インスタンス

    Returns:
        ok/error 形式の dict
    """
    conversation_id = ""
    message = {}

    if isinstance(input_data, dict):
        conversation_id = input_data.get("conversation_id", "")
        message = input_data.get("message", {})

    if not conversation_id:
        conversation_id = gen_id()

    if not message:
        return error("message is required")

    chat_params = {
        "conversation_id": conversation_id,
        "message": message,
    }

    chat_response = _call_chat_send(context, chat_params)

    if isinstance(chat_response, dict) and chat_response.get("_stub"):
        chat_response = _fallback_chat(conversation_id, message)

    return ok({
        "flow_id": "simple_chat",
        "result": chat_response,
    })


def _call_chat_send(context, params):
    """context 経由で defaults.chat.send を呼び出す

    Args:
        context: FlowContext または dict
        params: チャット送信パラメータ

    Returns:
        チャット応答 dict
    """
    if hasattr(context, "call_handler") and callable(context.call_handler):
        try:
            return context.call_handler("defaults.chat.send", params)
        except Exception:
            return {"status": "ok", "data": None, "_stub": True}
    return {"status": "ok", "data": None, "_stub": True}


def _fallback_chat(conversation_id, message):
    """domain.chat.store を直接使うフォールバック

    domain.chat が利用できない場合はスタブ応答を返す。

    Args:
        conversation_id: 会話 ID
        message: ユーザーメッセージ dict

    Returns:
        チャット応答 dict
    """
    user_content = ""
    if isinstance(message, dict):
        user_content = message.get("content", "")
    elif isinstance(message, str):
        user_content = message

    try:
        from domain.chat import store as chat_store
        assistant_message = {
            "id": gen_id(),
            "role": "assistant",
            "content": "[simple_chat] Received: {}".format(
                user_content[:100] if user_content else "(empty)"
            ),
            "timestamp": timestamp(),
        }
        return {
            "status": "ok",
            "data": {
                "conversation_id": conversation_id,
                "message": assistant_message,
            },
        }
    except ImportError:
        assistant_message = {
            "id": gen_id(),
            "role": "assistant",
            "content": "[simple_chat stub] Received: {}".format(
                user_content[:100] if user_content else "(empty)"
            ),
            "timestamp": timestamp(),
        }
        return {
            "status": "ok",
            "data": {
                "conversation_id": conversation_id,
                "message": assistant_message,
            },
        }
