from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

pytestmark = pytest.mark.contract


class _Manager:
    def get_system_prompt(self):
        return "System prompt"

    def get_prompt(self, prompt_id):
        return None

    def get_prompt_by_name(self, prompt_id):
        return None


def _setup_store(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore

    monkeypatch.setenv("RUMI_USER_DATA", str(tmp_path / "user_data"))
    monkeypatch.setenv(
        "RUMI_DEFAULTSPACK_CHAT_STORE_PATH",
        str(tmp_path / "user_data" / "shared" / "chat" / "conversations.json"),
    )
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


def test_directive_command_family_is_registered():
    from domain.frontend.command_registry import SlashCommandRegistry

    registry = SlashCommandRegistry(DEFAULTSPACK_ROOT)
    command = registry.find_command("directive")

    assert command is not None
    assert command["execution"]["type"] == "pack_block"
    assert command["execution"]["qualified_name"] == "defaultspack:directive.run"
    assert registry.find_command("developer")["id"] == "directive"
    assert registry.find_command("system")["id"] == "directive"
    assert registry.find_command("sytem")["id"] == "directive"


def test_directive_alias_persists_replaces_and_clears_conversation_metadata(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore
    from domain.frontend.command_registry import SlashCommandRegistry

    store = _setup_store(tmp_path, monkeypatch)
    conversation = store.create_conversation(model="stub/default")
    registry = SlashCommandRegistry(DEFAULTSPACK_ROOT)

    created = registry.execute(
        {
            "command": "developer",
            "mode": "chat",
            "conversation_id": conversation["id"],
            "args": {"instruction": "Use Japanese and cite concrete files."},
        },
        {},
    )
    assert created["status"] == "ok"
    assert created["data"]["executed"] is True

    stored = ChatStore().get_conversation(conversation["id"])
    directive = stored["metadata"]["directive_layer"]
    assert directive["content"] == "Use Japanese and cite concrete files."
    assert directive["scope"] == "conversation"
    assert directive["role"] == "developer"
    assert directive["source_command"] == "developer"

    replaced = registry.execute(
        {
            "command": "system",
            "mode": "chat",
            "conversation_id": conversation["id"],
            "args": {"instruction": "Act as a strict PR reviewer."},
        },
        {},
    )
    assert replaced["status"] == "ok"
    stored = ChatStore().get_conversation(conversation["id"])
    assert stored["metadata"]["directive_layer"]["content"] == "Act as a strict PR reviewer."
    assert stored["metadata"]["directive_layer"]["source_command"] == "system"

    cleared = registry.execute(
        {
            "command": "sytem",
            "mode": "chat",
            "conversation_id": conversation["id"],
            "args": {"instruction": "--clear"},
        },
        {},
    )
    assert cleared["status"] == "ok"
    assert cleared["data"]["result"]["cleared"] is True
    stored = ChatStore().get_conversation(conversation["id"])
    assert "directive_layer" not in stored["metadata"]
    ChatStore._instance = None


def test_prepare_chat_run_materializes_directive_above_user_content(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore
    from domain.frontend.command_registry import SlashCommandRegistry
    from domain.chat.run_request import prepare_chat_run

    store = _setup_store(tmp_path, monkeypatch)
    conversation = store.create_conversation(model="stub/default")
    registry = SlashCommandRegistry(DEFAULTSPACK_ROOT)
    registry.execute(
        {
            "command": "directive",
            "mode": "chat",
            "conversation_id": conversation["id"],
            "args": {"instruction": "Always surface blockers first."},
        },
        {},
    )

    prepared = prepare_chat_run(
        {"conversation_id": conversation["id"], "message": {"content": "Review this diff."}},
        {},
    )

    assert prepared.request_context["instruction_order"] == [
        "rumi_controller_directive",
        "conversation_directive",
        "normal_user_content",
    ]
    assert prepared.request_context["conversation_directive"]["content"] == (
        "Always surface blockers first."
    )
    serialized_messages = "\n\n".join(str(message.get("content") or "") for message in prepared.standard_messages)
    assert "[Developer instructions]" in serialized_messages
    assert "Always surface blockers first." in serialized_messages
    assert prepared.standard_messages[-1] == {"role": "user", "content": "Review this diff."}
    ChatStore._instance = None


def test_directive_context_helper_inserts_developer_after_rumi_system_layer():
    from domain.chat.directive_layer import (
        DIRECTIVE_METADATA_KEY,
        insert_conversation_directive_message,
    )

    messages = [
        {"role": "system", "content": "Rumi controller directive"},
        {"role": "user", "content": "normal user content"},
    ]
    directive = insert_conversation_directive_message(
        messages,
        {"metadata": {DIRECTIVE_METADATA_KEY: {"content": "Conversation rule"}}},
    )

    assert directive["content"] == "Conversation rule"
    assert [message["role"] for message in messages] == ["system", "developer", "user"]
    assert messages[0]["content"] == "Rumi controller directive"
    assert "Conversation rule" in messages[1]["content"]
