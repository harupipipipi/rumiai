from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def _reset_chat_store(monkeypatch, tmp_path):
    from domain.chat.store import ChatStore

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None
    return ChatStore()


def _add_messages(store, conversation_id, count):
    messages = []
    for index in range(count):
        role = "user" if index % 2 == 0 else "assistant"
        messages.append(
            store.add_message(
                conversation_id,
                {"role": role, "content": "message " + str(index)},
            )
        )
    return messages


def _add_tool_pair(store, conversation_id, call_id="call_1"):
    call = store.add_message(
        conversation_id,
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_call",
                    "id": call_id,
                    "name": "search_docs",
                    "arguments": "{}",
                }
            ],
        },
    )
    result = store.add_message(
        conversation_id,
        {
            "role": "tool",
            "content": [
                {
                    "type": "tool_result",
                    "tool_call_id": call_id,
                    "name": "search_docs",
                    "content": "ok",
                }
            ],
        },
    )
    return call, result


class _ScriptedAI:
    def __init__(self, *texts):
        self.texts = list(texts)
        self.requests = []

    def __call__(self, name, params):
        assert name == "defaults.ai.complete"
        self.requests.append(params)
        index = min(len(self.requests) - 1, len(self.texts) - 1)
        return {
            "status": "ok",
            "data": {"content": [{"type": "text", "text": self.texts[index]}]},
        }


def test_chat_store_filters_and_sorts_pinned_conversations(tmp_path, monkeypatch):
    from blocks.chat.list_conversations import run as list_conversations

    store = _reset_chat_store(monkeypatch, tmp_path)
    workspace = store.create_conversation(
        model="stub/default",
        tags=["alpha", "shared"],
        metadata={"company_id": "co-1", "workspace_id": "ws-1", "workspace_label": "Alpha Workspace"},
        conversation_kind="chat",
        group_id="group-a",
    )
    older_pin = store.create_conversation(model="stub/default", tags=["shared"], metadata={"company_id": "co-2"})
    newer_pin = store.create_conversation(model="stub/default", tags=["shared"], metadata={"company_id": "co-2"})

    store.update_conversation(workspace["id"], {"title": "Workspace Notes"})
    store.add_message(workspace["id"], {"role": "user", "content": "message-only needle"})
    store.update_conversation(older_pin["id"], {"title": "Older Pin", "is_pinned": True, "pinned_at": 1000})
    store.update_conversation(newer_pin["id"], {"title": "Newer Pin", "is_pinned": True, "pinned_at": 2000})
    store.update_conversation(workspace["id"], {"title": "Workspace Notes Updated"})

    pinned, total = store.list_conversations(is_pinned=True)
    assert total == 2
    assert [item["id"] for item in pinned] == [newer_pin["id"], older_pin["id"]]

    filtered, total = store.list_conversations(
        tag="alpha",
        tags=["shared"],
        company_id="co-1",
        workspace_id="ws-1",
        conversation_kind="chat",
        group_id="group-a",
        query="Alpha Workspace",
    )
    assert total == 1
    assert filtered[0]["id"] == workspace["id"]

    no_message_match, total = store.list_conversations(query="message-only")
    assert total == 0
    message_match, total = store.list_conversations(query="message-only", include_messages=True)
    assert total == 1
    assert message_match[0]["id"] == workspace["id"]

    block_result = list_conversations(
        {"query": "message-only", "include_messages": "true", "is_archived": "false", "is_pinned": "false"},
        {},
    )
    assert block_result["status"] == "ok"
    assert block_result["data"]["total"] == 1
    assert block_result["data"]["conversations"][0]["id"] == workspace["id"]

    from domain.chat.store import ChatStore

    ChatStore._instance = None


def test_chat_store_normalizes_legacy_conversations_with_pin_fields(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    storage_path.parent.mkdir(parents=True)
    storage_path.write_text(
        json.dumps(
            {
                "conversations": {
                    "legacy-1": {
                        "title": "Legacy",
                        "created_at": 10,
                        "updated_at": 20,
                        "model": "stub/default",
                        "messages": [],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None

    legacy = ChatStore().get_conversation("legacy-1")

    assert legacy["is_pinned"] is False
    assert legacy["pinned_at"] is None
    assert legacy["pin_scope"] == "global"
    ChatStore._instance = None


def test_chat_store_reloads_external_conversation_index_updates(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore

    store = _reset_chat_store(monkeypatch, tmp_path)
    conversation = store.create_conversation(model="stub/default")
    first_message = store.add_message(
        conversation["id"],
        {"role": "user", "content": [{"type": "text", "text": "original"}]},
    )
    storage_path = Path(os.environ["RUMI_DEFAULTSPACK_CHAT_STORE_PATH"])
    payload = json.loads(storage_path.read_text(encoding="utf-8"))
    external_message = {
        "id": "external-assistant-message",
        "conversation_id": conversation["id"],
        "parent_id": first_message["id"],
        "children_ids": [],
        "sequence_number": 2,
        "role": "assistant",
        "content": [{"type": "text", "text": "external reply"}],
        "raw_text": "external reply",
        "created_at": first_message["created_at"] + 1,
        "finish_reason": None,
        "usage": None,
        "widget": None,
        "metadata": None,
        "events": None,
        "tool_logs": None,
    }
    external_conversation = payload["conversations"][conversation["id"]]
    external_conversation["messages"].append(external_message)
    external_conversation["current_node_id"] = external_message["id"]
    external_conversation["updated_at"] = first_message["created_at"] + 2
    payload["updated_at"] = first_message["created_at"] + 2
    storage_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.utime(storage_path, (time.time() + 2, time.time() + 2))

    reloaded = store.get_conversation(conversation["id"])
    assert reloaded["current_node_id"] == "external-assistant-message"
    assert [message["id"] for message in reloaded["messages"]][-1] == "external-assistant-message"

    added = store.add_message(conversation["id"], {"role": "user", "content": "after external"})
    updated = store.get_conversation(conversation["id"])
    assert added["parent_id"] == "external-assistant-message"
    assert [message["id"] for message in updated["messages"]][-2:] == ["external-assistant-message", added["id"]]
    ChatStore._instance = None


def test_chat_compact_protects_last_messages(tmp_path, monkeypatch):
    from blocks.chat.compact import run as compact
    from domain.chat.store import ChatStore

    store = _reset_chat_store(monkeypatch, tmp_path)
    conversation = store.create_conversation(model="stub/default")
    messages = _add_messages(store, conversation["id"], 16)
    protected_ids = [message["id"] for message in messages[-4:]]

    result = compact({"conversation_id": conversation["id"], "protect_last_messages": 4}, {})

    assert result["status"] == "ok"
    data = result["data"]
    assert data["deleted_message_ids"] == [message["id"] for message in messages[:-4]]
    updated = ChatStore().get_conversation(conversation["id"])
    assert [message["id"] for message in updated["messages"][-4:]] == protected_ids
    assert len(updated["messages"]) == 5
    assert updated["messages"][0]["metadata"]["compact"] is True
    ChatStore._instance = None


def test_chat_compact_expands_explicit_range_to_keep_tool_pairs(tmp_path, monkeypatch):
    from blocks.chat.compact import run as compact
    from domain.chat.store import ChatStore

    store = _reset_chat_store(monkeypatch, tmp_path)
    conversation = store.create_conversation(model="stub/default")
    call, result = _add_tool_pair(store, conversation["id"])

    compacted = compact(
        {
            "conversation_id": conversation["id"],
            "start_message_id": result["id"],
            "end_message_id": result["id"],
            "protect_last_messages": 0,
        },
        {},
    )

    assert compacted["status"] == "ok"
    data = compacted["data"]
    assert data["deleted_message_ids"] == [call["id"], result["id"]]
    summary = data["summary_message"]
    assert summary["metadata"]["original_message_ids"] == [call["id"], result["id"]]
    ChatStore._instance = None


def test_oldest_compact_keeps_tool_pair_when_result_is_protected(tmp_path, monkeypatch):
    from blocks.chat._compact_helpers import select_oldest_safe_segment
    from domain.chat.store import ChatStore

    store = _reset_chat_store(monkeypatch, tmp_path)
    conversation = store.create_conversation(model="stub/default")
    old_messages = _add_messages(store, conversation["id"], 8)
    call, result = _add_tool_pair(store, conversation["id"], call_id="call_protected")
    tail = store.add_message(conversation["id"], {"role": "user", "content": "fresh tail"})
    conversation = ChatStore().get_conversation(conversation["id"])

    segment, err = select_oldest_safe_segment(conversation["messages"], protect_last_messages=2)

    assert err is None
    assert segment["end_id"] == old_messages[-1]["id"]
    assert call["id"] not in segment["original_message_ids"]
    assert result["id"] not in segment["original_message_ids"]
    assert tail["id"] not in segment["original_message_ids"]
    ChatStore._instance = None


def test_chat_compact_rejects_explicit_range_that_would_split_protected_tool_pair(tmp_path, monkeypatch):
    from blocks.chat.compact import run as compact
    from domain.chat.store import ChatStore

    store = _reset_chat_store(monkeypatch, tmp_path)
    conversation = store.create_conversation(model="stub/default")
    call, result = _add_tool_pair(store, conversation["id"], call_id="call_protected")

    compacted = compact(
        {
            "conversation_id": conversation["id"],
            "start_message_id": call["id"],
            "end_message_id": call["id"],
            "protect_last_messages": 1,
        },
        {},
    )

    assert compacted["status"] == "ok"
    assert compacted["data"]["deleted_message_ids"] == []
    assert compacted["data"]["message"] == "Selected range cannot be compacted safely"
    messages = ChatStore().get_conversation(conversation["id"])["messages"]
    assert [message["id"] for message in messages] == [call["id"], result["id"]]
    ChatStore._instance = None


def test_history_compact_ai_segment_expands_to_keep_tool_pair(tmp_path, monkeypatch):
    from blocks.chat.history.compact import run as compact_history
    from domain.chat.store import ChatStore

    store = _reset_chat_store(monkeypatch, tmp_path)
    conversation = store.create_conversation(model="stub/default")
    call, result = _add_tool_pair(store, conversation["id"], call_id="call_ai_range")
    store.add_message(conversation["id"], {"role": "user", "content": "tail " + ("x" * 160)})
    scripted = _ScriptedAI(
        json.dumps(
            [
                {
                    "start_id": result["id"],
                    "end_id": result["id"],
                    "reason": "tool result only",
                    "summary_preview": "unsafe half range",
                }
            ]
        )
    )

    compacted = compact_history(
        {"conversation_id": conversation["id"], "dry_run": True},
        {"call_handler": scripted},
    )

    assert compacted["status"] == "ok"
    assert len(scripted.requests) == 1
    request = scripted.requests[0]
    assert request["model"] == "stub/default"
    assert request["tools"] == []
    segments = compacted["data"]["trim_plan"]["segments"]
    assert segments == [
        {
            "start_id": call["id"],
            "end_id": result["id"],
            "reason": "tool result only",
            "summary_preview": "unsafe half range",
        }
    ]
    assert ChatStore().get_conversation(conversation["id"])["messages"][1]["id"] == result["id"]
    ChatStore._instance = None


def test_auto_compact_suggest_is_non_destructive(tmp_path, monkeypatch):
    from blocks.chat.auto_compact import run as auto_compact
    from domain.chat.store import ChatStore

    store = _reset_chat_store(monkeypatch, tmp_path)
    conversation = store.create_conversation(model="stub/default")
    messages = _add_messages(store, conversation["id"], 14)
    before_ids = [message["id"] for message in messages]

    result = auto_compact({"conversation_id": conversation["id"], "mode": "suggest", "protect_last_messages": 4}, {})

    assert result["status"] == "ok"
    assert result["data"]["compactable"] is True
    assert result["data"]["would_delete_message_ids"]
    after_ids = [message["id"] for message in ChatStore().get_conversation(conversation["id"])["messages"]]
    assert after_ids == before_ids
    ChatStore._instance = None


def test_auto_compact_apply_requires_approval_and_writes_summary_metadata(tmp_path, monkeypatch):
    from blocks.chat.auto_compact import run as auto_compact
    from domain.chat.store import ChatStore

    store = _reset_chat_store(monkeypatch, tmp_path)
    conversation = store.create_conversation(model="stub/default")
    messages = _add_messages(store, conversation["id"], 14)
    protected_ids = [message["id"] for message in messages[-5:]]

    rejected = auto_compact({"conversation_id": conversation["id"], "mode": "apply", "protect_last_messages": 5}, {})
    assert rejected["status"] == "error"
    assert rejected["error"]["code"] == "APPROVAL_REQUIRED"

    result = auto_compact(
        {"conversation_id": conversation["id"], "mode": "apply", "approved": True, "protect_last_messages": 5},
        {},
    )

    assert result["status"] == "ok"
    summary = result["data"]["summary_message"]
    metadata = summary["metadata"]
    assert metadata["is_summary"] is True
    assert metadata["compact"] is True
    assert metadata["model"] == "stub/default"
    assert metadata["protect_last_messages"] == 5
    assert metadata["original_message_ids"] == result["data"]["deleted_message_ids"]
    assert metadata["compacted_at"]
    assert metadata["content_ref"].startswith("chat://conversations/")
    updated = ChatStore().get_conversation(conversation["id"])
    assert [message["id"] for message in updated["messages"][-5:]] == protected_ids
    ChatStore._instance = None


def test_compact_slash_command_uses_chat_compact_when_conversation_id_is_present(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore
    from domain.frontend.command_registry import SlashCommandRegistry

    store = _reset_chat_store(monkeypatch, tmp_path)
    conversation = store.create_conversation(model="stub/default")
    _add_messages(store, conversation["id"], 13)

    result = SlashCommandRegistry(DEFAULTSPACK_ROOT).execute(
        {
            "command": "compact",
            "mode": "chat",
            "conversation_id": conversation["id"],
            "args": {"protect_last_messages": 3},
        },
        {},
    )

    assert result["status"] == "ok"
    assert result["data"]["executed"] is True
    assert result["data"]["result"]["deleted_count"] == 10
    assert result["data"]["result"]["summary_message"]["metadata"]["compact"] is True
    ChatStore._instance = None
