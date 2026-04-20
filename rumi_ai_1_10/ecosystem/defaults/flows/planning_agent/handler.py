"""planning_agent フローハンドラ

タスク分解→承認→順次実行を行うフロー。
最小動作版では defaults.chat.send を1回呼んで
「計画を立てました（スタブ）」を返す。
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from blocks._common import ok, error, gen_id, timestamp


def run(input_data, context):
    """プランニングエージェントフローのメイン処理

    最小動作版: defaults.chat.send を1回呼んでスタブの計画を返す。
    将来的にはタスク分解→承認→順次実行ループを実装する。

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
    planning_model = "stub/default"
    if hasattr(context, "get_config") and callable(context.get_config):
        agent_id_val = context.get_config("agent_id")
        if agent_id_val is not None:
            agent_id = agent_id_val
        model_val = context.get_config("planning_model")
        if model_val is not None:
            planning_model = model_val

    chat_params = {
        "conversation_id": conversation_id,
        "message": message,
        "agent_id": agent_id,
        "model": planning_model,
    }

    chat_response = _call_chat_send(context, chat_params)

    if isinstance(chat_response, dict) and chat_response.get("_stub"):
        chat_response = _fallback_chat(conversation_id, message, agent_id)

    plan = _generate_stub_plan(message)

    return ok({
        "flow_id": "planning_agent",
        "result": chat_response,
        "plan": plan,
        "agent_id": agent_id,
        "planning_model": planning_model,
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
                "content": "[planning_agent stub] Planning completed for: {}".format(
                    user_content[:100] if user_content else "(empty)"
                ),
                "timestamp": timestamp(),
            },
        },
    }


def _generate_stub_plan(message):
    """スタブの計画リストを生成する

    最小動作版では固定の3ステップ計画を返す。
    将来的には LLM を使ってタスクを分解する。

    Args:
        message: ユーザーメッセージ dict

    Returns:
        計画ステップの文字列リスト
    """
    user_content = ""
    if isinstance(message, dict):
        user_content = message.get("content", "")
    elif isinstance(message, str):
        user_content = message

    task_summary = user_content[:50] if user_content else "task"

    return [
        "Step 1: Analyze - Understand the request: {}".format(task_summary),
        "Step 2: Implement - Execute the planned actions",
        "Step 3: Verify - Confirm results and report back",
    ]
