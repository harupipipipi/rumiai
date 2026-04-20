import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import ok, error, gen_id
from domain.ai_client.client import AIClient
from domain.dev.inspector import Inspector
from domain.prompt.manager import get_manager


def run(input_data, context):
    model = input_data.get("model")
    messages = input_data.get("messages")
    if not model:
        return error("model is required", "MISSING_PARAM")
    if not messages:
        return error("messages is required", "MISSING_PARAM")
    tools = input_data.get("tools", [])
    params = input_data.get("params", {})

    # P1-4: Inspector 用のリクエストID を生成
    request_id = gen_id()

    try:
        client = AIClient()
        result = client.complete(model, messages, tools=tools, params=params)
    except RuntimeError as e:
        return error(str(e), "PROVIDER_ERROR")

    # P1-4: Inspector にリクエストログを記録
    try:
        inspector = Inspector()
        manager = get_manager()
        system_prompt = manager.get_system_prompt()

        # メッセージからシステムプロンプトを抽出（もしあれば）
        prompt_used = system_prompt
        for msg in messages:
            if msg.get("role") == "system":
                prompt_used = msg.get("content", system_prompt)
                break

        # 使用されたツール名を抽出
        tools_called = []
        if tools:
            for t in tools:
                if isinstance(t, dict):
                    tool_name = t.get("name", t.get("function", {}).get("name", ""))
                    if tool_name:
                        tools_called.append(tool_name)
                elif isinstance(t, str):
                    tools_called.append(t)

        conversation_id = input_data.get("conversation_id", "")

        inspector.log_request(
            request_id=request_id,
            conversation_id=conversation_id,
            model=model,
            prompt_used=prompt_used,
            tools_called=tools_called,
            context_info={
                "message_count": len(messages),
                "source": "blocks.ai.complete",
                "params": params,
            },
        )
    except Exception:
        pass  # Inspector のエラーで本来の処理を止めない

    return ok(result)
