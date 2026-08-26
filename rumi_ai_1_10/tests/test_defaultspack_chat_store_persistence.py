from __future__ import annotations

import errno
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_chat_store_startup_skips_best_effort_history_backfill_when_disk_is_full(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    storage_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "updated_at": 0,
                "conversations": {
                    "conv-1": {
                        "id": "conv-1",
                        "title": "Recovered Conversation",
                        "created_at": 0,
                        "updated_at": 0,
                        "model": "stub/default",
                        "messages": [],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None

    def fail_backfill(self):
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(ChatStore, "_save_conversation_files", fail_backfill)

    store = ChatStore()

    assert store.get_conversation("conv-1")["title"] == "Recovered Conversation"
    ChatStore._instance = None


def test_chat_store_update_saves_only_changed_conversation_history(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None

    store = ChatStore()
    first = store.create_conversation(model="stub/default")
    second = store.create_conversation(model="stub/default")
    saved_conversation_ids = []

    def record_save(self, conversation_id, conversation):
        saved_conversation_ids.append(str(conversation_id))

    monkeypatch.setattr(ChatStore, "_save_conversation_file", record_save)

    updated = store.update_conversation(first["id"], {"title": "Only First Updated"})

    assert updated["title"] == "Only First Updated"
    assert saved_conversation_ids == [first["id"]]
    assert second["id"] not in saved_conversation_ids
    ChatStore._instance = None


def test_chat_store_list_conversations_omits_full_messages_by_default(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None

    store = ChatStore()
    conversation = store.create_conversation(model="stub/default")
    store.add_message(conversation["id"], {"role": "user", "content": [{"type": "text", "text": "hello world"}]})

    listed, total = store.list_conversations(limit=10, include_messages=False)

    assert total == 1
    assert listed[0]["id"] == conversation["id"]
    assert listed[0]["messages"] == []
    assert listed[0]["message_count"] == 1
    assert listed[0]["last_message_preview"] == "hello world"
    ChatStore._instance = None


def test_chat_store_list_conversations_iterates_snapshot_when_store_changes(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None

    store = ChatStore()
    first = store.create_conversation(model="stub/default")
    second = store.create_conversation(model="stub/default")
    original_normalize = ChatStore._normalize_conversation
    injected = {"done": False}

    def normalize_and_change_store(conversation_id, conversation):
        original_normalize(conversation_id, conversation)
        if not injected["done"]:
            injected["done"] = True
            store._conversations["conv-added-during-list"] = {
                "id": "conv-added-during-list",
                "title": "Added During List",
                "created_at": 0,
                "updated_at": 0,
                "model": "stub/default",
                "messages": [],
            }

    monkeypatch.setattr(ChatStore, "_normalize_conversation", staticmethod(normalize_and_change_store))

    listed, total = store.list_conversations(limit=10, include_messages=False)

    assert total == 2
    assert {conversation["id"] for conversation in listed} == {first["id"], second["id"]}
    ChatStore._instance = None


def test_chat_store_update_replaces_client_supplied_icon_svg(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None

    store = ChatStore()
    conversation = store.create_conversation(model="stub/default")
    payload = (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'onload="globalThis.__rumi_xss=1"></svg>'
    )

    updated = store.update_conversation(
        conversation["id"],
        {"metadata": {"icon_svg": payload, "workspace_label": "Local"}},
    )

    assert updated["metadata"]["workspace_label"] == "Local"
    assert updated["metadata"]["icon_svg"] != payload
    assert "onload" not in updated["metadata"]["icon_svg"].lower()
    ChatStore._instance = None


def test_chat_store_load_replaces_persisted_icon_svg(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'onload="globalThis.__rumi_xss=1"></svg>'
    )
    storage_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "updated_at": 0,
                "conversations": {
                    "conv-1": {
                        "id": "conv-1",
                        "title": "Recovered Conversation",
                        "created_at": 0,
                        "updated_at": 0,
                        "model": "stub/default",
                        "metadata": {"icon_svg": payload, "workspace_label": "Local"},
                        "messages": [],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None

    conversation = ChatStore().get_conversation("conv-1")

    assert conversation["metadata"]["workspace_label"] == "Local"
    assert conversation["metadata"]["icon_svg"] != payload
    assert "onload" not in conversation["metadata"]["icon_svg"].lower()
    ChatStore._instance = None
