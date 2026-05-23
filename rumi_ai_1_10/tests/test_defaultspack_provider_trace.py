from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_provider_trace_redacts_api_keys_and_images(tmp_path, monkeypatch):
    from domain.ai_client.provider_trace import write_provider_trace
    from domain.chat.store import ChatStore

    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(tmp_path / "user_data" / "shared" / "chat" / "conversations.json"))
    ChatStore._instance = None
    store = ChatStore()
    conv = store.create_conversation(model="stub/default")

    meta = write_provider_trace(
        conversation_id=conv["id"],
        request_id="req",
        provider="openai",
        model="gpt",
        api_family="openai_chat",
        ir_schema_version="rumi.chat.ir.v2",
        capability_summary={},
        planning_metadata={"token": "secret-value"},
        dropped_features=[{"feature": "image"}],
        bridge_actions=[],
        warnings=[],
        compiled_payload={"headers": {"Authorization": "Bearer sk-secret"}, "image": "data:image/png;base64,abcd"},
        response_summary={"finish_reason": "stop"},
        store=store,
    )
    payload = json.loads(Path(meta["trace_path"]).read_text(encoding="utf-8"))

    assert payload["planning_metadata"]["token"] == "[REDACTED]"
    assert payload["compiled_payload"]["headers"]["Authorization"] == "[REDACTED]"
    assert payload["compiled_payload"]["image"] == "data:image/png;base64,[REDACTED:4 chars]"
    assert payload["dropped_features"][0]["feature"] == "image"
    ChatStore._instance = None
