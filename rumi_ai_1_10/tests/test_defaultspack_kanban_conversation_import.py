from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def _reset_stores(monkeypatch, tmp_path):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(tmp_path / "chat" / "conversations.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_KANBAN_DB_PATH", str(tmp_path / "kanban.db"))

    from domain.chat.store import ChatStore
    from domain.kanban.store import KanbanStore

    ChatStore._instance = None
    KanbanStore._instance = None
    return ChatStore


def test_import_conversation_creates_group_board_cards_and_prompt_note(tmp_path, monkeypatch):
    ChatStore = _reset_stores(monkeypatch, tmp_path)

    from domain.kanban.service import KanbanService, append_kanban_system_prompt_note

    chat_store = ChatStore()
    conversation = chat_store.create_conversation(model="stub/default", group_id="group-alpha")
    conversation = chat_store.update_conversation(
        conversation["id"],
        {
            "title": "Launch checklist",
            "metadata": {"group_id": "group-alpha", "workspace_id": "workspace-1"},
        },
    )
    chat_store.add_message(
        conversation["id"],
        {
            "role": "user",
            "content": [{"type": "text", "text": "TODO: write release notes"}],
            "raw_text": "TODO: write release notes",
        },
    )

    service = KanbanService()
    board = service.bootstrap_board({"scope_type": "group", "scope_id": "group-alpha"})["board"]
    imported = service.import_conversation(board["board_id"], {"conversation_id": conversation["id"], "use_ai": False})

    assert imported["board"]["scope_type"] == "group"
    assert imported["cards"][0]["conversation_id"] == conversation["id"]
    assert imported["cards"][0]["source_type"] == "conversation"
    assert imported["cards"][0]["title"] == "write release notes"
    assert imported["cards"][0]["metadata"]["conversation_group_id"] == "group-alpha"

    updated = chat_store.get_conversation(conversation["id"])
    assert updated["metadata"]["kanban"]["added"] is True
    assert updated["metadata"]["kanban"]["board_id"] == board["board_id"]
    prompt = append_kanban_system_prompt_note("base prompt", updated)
    assert "base prompt" in prompt
    assert "Kanbanに追加されています" in prompt


def test_synced_conversation_updates_existing_kanban_board(tmp_path, monkeypatch):
    ChatStore = _reset_stores(monkeypatch, tmp_path)

    from domain.kanban.chat_sync import sync_conversation_kanban
    from domain.kanban.service import KanbanService

    chat_store = ChatStore()
    conversation = chat_store.create_conversation(model="stub/default", group_id="group-alpha")
    conversation = chat_store.update_conversation(
        conversation["id"],
        {
            "title": "Task sync",
            "metadata": {"group_id": "group-alpha"},
        },
    )
    chat_store.add_message(
        conversation["id"],
        {
            "role": "user",
            "content": [{"type": "text", "text": "TODO: initial task"}],
            "raw_text": "TODO: initial task",
        },
    )

    service = KanbanService()
    board = service.bootstrap_board({"scope_type": "group", "scope_id": "group-alpha"})["board"]
    first = service.import_conversation(board["board_id"], {"conversation_id": conversation["id"], "use_ai": False})
    assert [card["title"] for card in first["cards"]] == ["initial task"]

    chat_store.add_message(
        conversation["id"],
        {
            "role": "user",
            "content": [{"type": "text", "text": "TODO: browser QA"}],
            "raw_text": "TODO: browser QA",
        },
    )
    synced = sync_conversation_kanban(conversation["id"], reason="test")

    assert synced is not None
    titles = [card["title"] for card in synced["cards"]]
    assert "initial task" in titles
    assert "browser QA" in titles


def test_import_conversation_ai_timeout_falls_back(tmp_path, monkeypatch):
    ChatStore = _reset_stores(monkeypatch, tmp_path)

    from domain.ai_client.client import AIClient
    from domain.kanban.service import KanbanService

    def slow_complete(self, model, messages, tools=None, params=None):
        del self, model, messages, tools, params
        time.sleep(0.2)
        return {"text": "{\"tasks\": []}"}

    monkeypatch.setattr(AIClient, "complete", slow_complete)

    chat_store = ChatStore()
    conversation = chat_store.create_conversation(model="stub/default", group_id="group-alpha")
    conversation = chat_store.update_conversation(conversation["id"], {"title": "Timeout fallback"})
    chat_store.add_message(
        conversation["id"],
        {
            "role": "user",
            "content": [{"type": "text", "text": "TODO: keep UI responsive"}],
            "raw_text": "TODO: keep UI responsive",
        },
    )

    service = KanbanService()
    board = service.bootstrap_board({"scope_type": "conversation", "scope_id": conversation["id"]})["board"]
    imported = service.import_conversation(
        board["board_id"],
        {
            "conversation_id": conversation["id"],
            "model": "stub/default",
            "ai_timeout_seconds": 0.01,
            "_authority_context": {"test": True},
        },
    )

    assert imported["cards"][0]["title"] == "keep UI responsive"
    assert imported["cards"][0]["metadata"]["conversation_import"]["extraction"]["source"] == "fallback"
    assert "timed out" in imported["cards"][0]["metadata"]["conversation_import"]["extraction"]["error"]


def test_import_conversation_without_authority_context_skips_ai(tmp_path, monkeypatch):
    ChatStore = _reset_stores(monkeypatch, tmp_path)

    from domain.ai_client.client import AIClient
    from domain.kanban.service import KanbanService

    def fail_complete(self, model, messages, tools=None, params=None):
        del self, model, messages, tools, params
        raise AssertionError("AI should not run without authority context")

    monkeypatch.setattr(AIClient, "complete", fail_complete)

    chat_store = ChatStore()
    conversation = chat_store.create_conversation(model="stub/default")
    conversation = chat_store.update_conversation(conversation["id"], {"title": "Authority fallback"})
    chat_store.add_message(
        conversation["id"],
        {
            "role": "user",
            "content": [{"type": "text", "text": "TODO: stay local first"}],
            "raw_text": "TODO: stay local first",
        },
    )

    service = KanbanService()
    board = service.bootstrap_board({"scope_type": "conversation", "scope_id": conversation["id"]})["board"]
    imported = service.import_conversation(
        board["board_id"],
        {"conversation_id": conversation["id"], "model": "stub/default"},
    )

    extraction = imported["cards"][0]["metadata"]["conversation_import"]["extraction"]
    assert imported["cards"][0]["title"] == "stay local first"
    assert extraction["source"] == "fallback"
    assert extraction["reason"] == "authority_context_missing"
