from __future__ import annotations

import sys
from pathlib import Path

DEFAULTSPACK_ROOT = Path(__file__).resolve().parents[1] / "ecosystem" / "defaultspack"
if str(DEFAULTSPACK_ROOT) not in sys.path:
    sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.chat.conversation_channel import (  # noqa: E402
    SIDE_CHAT_SYSTEM_INSTRUCTION,
    conversation_channel_system_instruction,
    runtime_conversation,
)
from domain.chat.store import ChatStore  # noqa: E402


def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "RUMI_DEFAULTSPACK_CHAT_STORE_PATH",
        str(tmp_path / "chat" / "conversations.json"),
    )
    ChatStore._instance = None
    return ChatStore()


def test_side_chat_creation_is_deduplicated_and_hidden(tmp_path, monkeypatch):
    store = isolated_store(tmp_path, monkeypatch)
    parent = store.create_conversation(
        model="provider/main",
        metadata={"workspace_id": "workspace"},
    )

    first = store.create_conversation(
        model="provider/main",
        parent_conversation_id=parent["id"],
        conversation_kind="side",
        metadata={"hidden": True, "conversation_channel": "side"},
    )
    second = store.create_conversation(
        model="provider/main",
        parent_conversation_id=parent["id"],
        conversation_kind="side",
        metadata={"hidden": True, "conversation_channel": "side"},
    )

    assert first["id"] == second["id"]
    visible, total = store.list_conversations(include_messages=False)
    assert total == 1
    assert [item["id"] for item in visible] == [parent["id"]]


def test_side_runtime_inherits_parent_without_merging_history(tmp_path, monkeypatch):
    store = isolated_store(tmp_path, monkeypatch)
    parent = store.create_conversation(
        model="provider/main",
        system_prompt_id="main-system",
        agent_id="main-agent",
        group_id="main-group",
        metadata={
            "workspace_id": "workspace",
            "workspace_root": "/workspace",
            "tool_preferences": {"mode": "manual"},
        },
    )
    side = store.create_conversation(
        model="provider/stale",
        parent_conversation_id=parent["id"],
        conversation_kind="side",
        metadata={"hidden": True, "conversation_channel": "side"},
    )
    store.add_message(side["id"], {"role": "user", "content": "side-only"})

    runtime = runtime_conversation(store, store.get_conversation(side["id"]))

    assert runtime["id"] == side["id"]
    assert runtime["model"] == "provider/main"
    assert runtime["system_prompt_id"] == "main-system"
    assert runtime["agent_id"] == "main-agent"
    assert runtime["group_id"] == "main-group"
    assert runtime["metadata"]["workspace_id"] == "workspace"
    assert runtime["metadata"]["tool_preferences"] == {"mode": "manual"}
    assert runtime["messages"][0]["content"] == "side-only"
    assert conversation_channel_system_instruction(runtime) == SIDE_CHAT_SYSTEM_INSTRUCTION


def test_deleting_parent_cascades_only_owned_side_chat(tmp_path, monkeypatch):
    store = isolated_store(tmp_path, monkeypatch)
    parent = store.create_conversation(model="provider/main")
    side = store.create_conversation(
        parent_conversation_id=parent["id"],
        conversation_kind="side",
        metadata={"hidden": True, "conversation_channel": "side"},
    )
    worker = store.create_conversation(
        parent_conversation_id=parent["id"],
        conversation_kind="subagent",
    )

    assert store.delete_conversation(parent["id"]) is True
    assert store.get_conversation(side["id"]) is None
    remaining_worker = store.get_conversation(worker["id"])
    assert remaining_worker is not None
    assert remaining_worker["parent_conversation_id"] is None
