from __future__ import annotations

import base64
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


class _Manager:
    def get_system_prompt(self):
        return "System prompt"

    def get_prompt(self, prompt_id):
        return None

    def get_prompt_by_name(self, prompt_id):
        return None


def _setup_store(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore

    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(tmp_path / "user_data" / "shared" / "chat" / "conversations.json"))
    ChatStore._instance = None
    store = ChatStore()
    monkeypatch.setattr("domain.chat.run_request.get_manager", lambda: _Manager())
    monkeypatch.setattr(
        "domain.chat.run_request.enrich_messages",
        lambda messages, system_prompt, conversation_id, user_text, manager: {
            "knowledge_text": "",
            "memory_text": "",
            "knowledge_results": [],
            "memory_results": [],
            "enriched_prompt": system_prompt,
        },
    )
    return store


def test_prepare_chat_run_creates_message_chain_ir_and_context(tmp_path, monkeypatch):
    from domain.chat.run_request import prepare_chat_run
    from domain.chat.store import ChatStore

    store = _setup_store(tmp_path, monkeypatch)
    conv = store.create_conversation(model="stub/default")
    store.add_message(conv["id"], {"role": "user", "content": [{"type": "text", "text": "old"}]})

    prepared = prepare_chat_run({"conversation_id": conv["id"], "message": {"content": "new"}}, {})

    assert prepared.user_message["content"] == [{"type": "text", "text": "new"}]
    assert prepared.standard_messages[0] == {"role": "system", "content": "System prompt"}
    assert prepared.standard_messages[-1] == {"role": "user", "content": "new"}
    assert prepared.chat_ir.schema_version == "rumi.chat.ir.v2"
    assert prepared.provider_planning["model"] == "stub/default"
    assert prepared.request_context["conversation_workspace_dir"]
    assert prepared.tool_context["history_json_path"].endswith("history.json")
    assert prepared.request_context["chat_references"]["conversation_id"] == conv["id"]
    ChatStore._instance = None


def test_prepare_chat_run_persists_sanitizes_and_inlines_attachments(tmp_path, monkeypatch):
    from domain.chat.run_request import prepare_chat_run
    from domain.chat.store import ChatStore

    store = _setup_store(tmp_path, monkeypatch)
    conv = store.create_conversation(model="stub/default")
    data_url = "data:image/png;base64," + base64.b64encode(b"abc").decode()

    prepared = prepare_chat_run(
        {
            "conversation_id": conv["id"],
            "message": {
                "content": "files",
                "attachments": [
                    {"id": "t", "name": "a.txt", "type": "text/plain", "content": "file text"},
                    {"id": "i", "name": "i.png", "type": "image/png", "size": 3, "dataUrl": data_url},
                ],
            },
        },
        {},
    )

    assert prepared.metadata["attachments"][1] == {"id": "i", "name": "i.png", "size": 3, "type": "image/png"}
    assert len(prepared.metadata["workspace_attachments"]) == 2
    assert any("file text" in block.get("text", "") for block in prepared.content if isinstance(block, dict))
    assert any(block.get("type") == "image_url" for block in prepared.content if isinstance(block, dict))
    assert any(block.type == "image_url" for message in prepared.chat_ir.messages for block in message.content)
    ChatStore._instance = None


def test_prepare_chat_run_current_turn_history_only_still_works(tmp_path, monkeypatch):
    from domain.chat.run_request import prepare_chat_run
    from domain.chat.store import ChatStore

    store = _setup_store(tmp_path, monkeypatch)
    conv = store.create_conversation(model="stub/default")
    store.add_message(conv["id"], {"role": "user", "content": [{"type": "text", "text": "old"}]})

    prepared = prepare_chat_run({"conversation_id": conv["id"], "message": {"content": "only"}}, {"chat_history_mode": "current_turn"})

    user_messages = [message for message in prepared.standard_messages if message.get("role") == "user"]
    assert user_messages == [{"role": "user", "content": "only"}]
    assert len(prepared.chat_ir.messages) == 1
    ChatStore._instance = None
