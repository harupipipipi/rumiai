import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import ok, error, gen_id
from domain.ai_client.client import AIClient
from domain.ai_client.model_runtime_settings import ModelRuntimeSettingsService
from domain.ai_client.stream_handler import StreamHandler


def run(input_data, context):
    model = input_data.get("model")
    messages = input_data.get("messages")
    if not model:
        return error("model is required", "MISSING_PARAM")
    if not messages:
        return error("messages is required", "MISSING_PARAM")
    tools = input_data.get("tools", [])
    params = dict(input_data.get("params") or {})
    if "thinking_level" not in params:
        params["thinking_level"] = ModelRuntimeSettingsService().get_effective_thinking_level(
            profile_id=model,
            conversation_id=input_data.get("conversation_id"),
        )["level"]

    stream_id = gen_id()

    try:
        client = AIClient()
        chunks = client.stream(model, messages, tools=tools, params=params)
        handler = StreamHandler(context)
        handler.send_chunks(stream_id, chunks)
        return ok({"stream_id": stream_id})
    except RuntimeError as e:
        return error(str(e), "PROVIDER_ERROR")
