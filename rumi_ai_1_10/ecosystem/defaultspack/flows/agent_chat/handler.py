"""agent_chat フローハンドラ

ツール使用可能なエージェントチャットループ。
最小動作版では defaults.chat.send を1回呼んで返す。
ツールループは agent 実装時に拡張する。
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from blocks._common import ok, error, gen_id, timestamp


def run(input_data, context):
    """エージェントチャットフローのメイン処理

    最小動作版: defaults.chat.send を1回呼んで結果を返す。
    将来的にはツール呼び出しループを実装する。

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

    agent_id = "default_agent"
    max_iterations = 10
    if hasattr(context, "get_config") and callable(context.get_config):
        agent_id_val = context.get_config("agent_id")
        if agent_id_val is not None:
            agent_id = agent_id_val
        max_iter_val = context.get_config("max_iterations")
        if max_iter_val is not None:
            try:
                max_iterations = int(max_iter_val)
            except (ValueError, TypeError):
                max_iterations = 10

    chat_params = {
        "conversation_id": conversation_id,
        "message": message,
        "agent_id": agent_id,
    }

    chat_response = _call_chat_send(context, chat_params)

    if isinstance(chat_response, dict) and chat_response.get("_stub"):
        chat_response = _fallback_chat(conversation_id, message, agent_id)

    return ok({
        "flow_id": "agent_chat",
        "result": chat_response,
        "agent_id": agent_id,
        "iterations_used": 1,
        "max_iterations": max_iterations,
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


def _fallback_chat(conversation_id, message, agent_id):
    """フォールバックチャット応答を生成する

    Args:
        conversation_id: 会話 ID
        message: ユーザーメッセージ dict
        agent_id: エージェント ID

    Returns:
        チャット応答 dict
    """
    user_content = ""
    if isinstance(message, dict):
        user_content = message.get("content", "")
    elif isinstance(message, str):
        user_content = message

    return {
        "status": "ok",
        "data": {
            "conversation_id": conversation_id,
            "message": {
                "id": gen_id(),
                "role": "assistant",
                "content": "[agent_chat stub] agent={} | Received: {}".format(
                    agent_id,
                    user_content[:100] if user_content else "(empty)",
                ),
                "timestamp": timestamp(),
            },
        },
    }
