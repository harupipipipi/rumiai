from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def _column_by_title(snapshot, title):
    return next(column for column in snapshot["columns"] if column["title"] == title)


def test_kanban_fallback_route_specs_are_registered():
    from ecosystem.defaultspack.transport.registry import _FALLBACK_HTTP_ROUTE_SPECS

    routes = {
        (spec.method, spec.pattern): (
            spec.block_module,
            spec.path_inject,
            spec.defaults.get("action"),
        )
        for spec in _FALLBACK_HTTP_ROUTE_SPECS
    }
    expected = {
        ("GET", "/api/kanban/boards"): ({}, "list_boards"),
        ("POST", "/api/kanban/boards/bootstrap"): ({}, "bootstrap_board"),
        ("GET", "/api/kanban/boards/{board_id}"): ({"board_id": "board_id"}, "get_board"),
        ("PUT", "/api/kanban/boards/{board_id}"): ({"board_id": "board_id"}, "update_board"),
        ("POST", "/api/kanban/boards/{board_id}/cards"): ({"board_id": "board_id"}, "create_card"),
        ("POST", "/api/kanban/boards/{board_id}/import-conversation"): ({"board_id": "board_id"}, "import_conversation"),
        ("PUT", "/api/kanban/cards/{card_id}"): ({"card_id": "card_id"}, "update_card"),
        ("DELETE", "/api/kanban/cards/{card_id}"): ({"card_id": "card_id"}, "delete_card"),
        ("POST", "/api/kanban/cards/{card_id}/move"): ({"card_id": "card_id"}, "move_card"),
        ("POST", "/api/kanban/cards/{card_id}/agent/start"): ({"card_id": "card_id"}, "agent_start"),
        ("GET", "/api/kanban/cards/{card_id}/agent/status"): ({"card_id": "card_id"}, "agent_status"),
        ("POST", "/api/kanban/cards/{card_id}/agent/ready"): ({"card_id": "card_id"}, "agent_ready"),
        ("POST", "/api/kanban/cards/{card_id}/agent/apply"): ({"card_id": "card_id"}, "agent_apply"),
        ("POST", "/api/kanban/cards/{card_id}/agent/dismiss"): ({"card_id": "card_id"}, "agent_dismiss"),
    }

    for route, (path_inject, action) in expected.items():
        assert route in routes
        block_module, actual_inject, actual_action = routes[route]
        assert block_module == "blocks.kanban.api"
        assert actual_inject == path_inject
        assert actual_action == action


def test_kanban_routes_dispatch_to_handler_with_defaults():
    from ecosystem.defaultspack.transport.http import DefaultsHttpServer

    server = DefaultsHttpServer(facade=None)
    calls = []

    def fake_invoke(module_name, request_data, path_params, inject=None):
        calls.append(
            {
                "module_name": module_name,
                "request_data": request_data,
                "path_params": path_params,
                "inject": inject or {},
            }
        )
        return {"status": "ok", "data": {"seen": True}}

    server._invoke_fallback_block = fake_invoke
    handler, params, source, path_inject, pattern = server._match_route(
        "POST",
        "/api/kanban/cards/kcard_1/agent/start",
    )

    assert handler is not None
    assert source == "fallback"
    assert pattern == "/api/kanban/cards/{card_id}/agent/start"
    assert params == {"card_id": "kcard_1"}
    assert path_inject == {"card_id": "card_id"}
    assert handler({"task": "work"}, params) == {"status": "ok", "data": {"seen": True}}
    assert calls == [
        {
            "module_name": "blocks.kanban.api",
            "request_data": {"task": "work", "action": "agent_start", "_method": "POST"},
            "path_params": {"card_id": "kcard_1"},
            "inject": {"card_id": "card_id"},
        }
    ]


def test_kanban_block_handler_bootstraps_and_mutates_board(tmp_path, monkeypatch):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_KANBAN_DB_PATH", str(tmp_path / "kanban.db"))

    from blocks.kanban.api import run
    from ecosystem.rumi_kanban_state_store_pack.runtime.store import KanbanStateStore

    owner_context = {"kanban_state_store_factory": KanbanStateStore}

    bootstrapped = run(
        {
            "_method": "GET",
            "scope_type": "conversation",
            "scope_id": "conv-1",
            "bootstrap": "true",
        },
        owner_context,
    )
    assert bootstrapped["status"] == "ok"
    snapshot = bootstrapped["data"]
    assert snapshot["board"]["scope_type"] == "conversation"
    assert [column["title"] for column in snapshot["columns"]] == ["Backlog", "Doing", "Review", "Done"]

    board_id = snapshot["board"]["board_id"]
    created = run(
        {"action": "create_card", "board_id": board_id, "title": "Finish API"},
        owner_context,
    )
    assert created["status"] == "ok"
    card = created["data"]
    assert card["title"] == "Finish API"

    started = run(
        {
            "action": "agent_start",
            "card_id": card["card_id"],
            "task": "Finish API",
            "model": "local",
        },
        owner_context,
    )
    assert started["status"] == "ok"
    assert started["data"]["agent_status"] == "running"
    assert started["data"]["column_id"] == _column_by_title(snapshot, "Doing")["column_id"]

    ready = run(
        {"action": "agent_ready", "card_id": card["card_id"]},
        owner_context,
    )
    assert ready["status"] == "ok"
    assert ready["data"]["agent_status"] == "ready"
    assert ready["data"]["column_id"] == _column_by_title(snapshot, "Review")["column_id"]

    applied = run(
        {"action": "agent_apply", "card_id": card["card_id"]},
        owner_context,
    )
    assert applied["status"] == "ok"
    assert applied["data"]["agent_status"] == "applied"
    assert applied["data"]["column_id"] == _column_by_title(snapshot, "Done")["column_id"]

    synced = run({"action": "sync_runs", "board_id": board_id}, owner_context)
    assert synced["status"] == "ok"
    assert synced["data"]["board"]["board_id"] == board_id
    assert any(event["event_type"] == "runs.sync.noop" for event in synced["data"]["events"])
