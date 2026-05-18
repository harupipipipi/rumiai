import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import ok


def run(input_data, context):
    del context
    data = input_data if isinstance(input_data, dict) else {}
    workspace = data.get("workspace") if isinstance(data.get("workspace"), dict) else {}
    user_data_dir = Path(str(workspace.get("user_data_dir") or ""))
    if user_data_dir:
        user_data_dir.mkdir(parents=True, exist_ok=True)
        event_path = user_data_dir / "chat_turns.jsonl"
        record = {
            "ts": int(time.time()),
            "conversation_id": data.get("conversation_id"),
            "message": data.get("message"),
            "ai_response": data.get("ai_response"),
            "route_model": data.get("route_model"),
        }
        with event_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return ok({"persisted": True, "conversation_id": data.get("conversation_id")})
