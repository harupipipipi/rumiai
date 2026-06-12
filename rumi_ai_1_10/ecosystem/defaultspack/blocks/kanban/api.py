from __future__ import annotations

from typing import Any

from blocks._common import error, ok
from domain.kanban.models import KanbanError
from domain.kanban.service import KanbanService


def run(input_data: Any, context: Any = None) -> dict[str, Any]:
    del context
    if not isinstance(input_data, dict):
        return _invalid("input_data must be a dict")
    payload = dict(input_data)
    action = _action(payload)
    service = KanbanService()
    try:
        if action in {"list_boards", "boards"}:
            return ok(service.list_boards(payload))
        if action in {"bootstrap_board", "bootstrap"}:
            return ok(service.bootstrap_board(payload))
        if action == "get_board":
            return ok(service.get_board(_board_id(payload)))
        if action == "update_board":
            return ok(service.update_board(_board_id(payload), payload))
        if action == "create_card":
            return ok(service.create_card(_board_id(payload), payload))
        if action == "update_card":
            return ok(service.update_card(_card_id(payload), payload))
        if action == "delete_card":
            return ok(service.delete_card(_card_id(payload)))
        if action == "move_card":
            return ok(service.move_card(_card_id(payload), payload))
        if action == "create_column":
            return ok(service.create_column(_board_id(payload), payload))
        if action == "update_column":
            return ok(service.update_column(_column_id(payload), payload))
        if action == "delete_column":
            return ok(service.delete_column(_column_id(payload)))
        if action in {"sync_runs", "sync"}:
            return ok(service.sync_runs(_board_id(payload), payload))
        if action in {"import_conversation", "sync_conversation"}:
            return ok(service.import_conversation(_board_id(payload), payload))
        if action == "agent_start":
            return ok(service.agent_start(_card_id(payload), payload))
        if action == "agent_status":
            return ok(service.agent_status(_card_id(payload)))
        if action == "agent_ready":
            return ok(service.agent_ready(_card_id(payload), payload))
        if action == "agent_apply":
            return ok(service.agent_apply(_card_id(payload), payload))
        if action == "agent_dismiss":
            return ok(service.agent_dismiss(_card_id(payload), payload))
        return _invalid("unsupported kanban action: " + action)
    except KanbanError as exc:
        response = error(str(exc), getattr(exc, "code", "KANBAN_ERROR"))
        response["_http_status"] = int(getattr(exc, "http_status", 400))
        return response
    except Exception as exc:
        return error("kanban API failed: " + str(exc), "KANBAN_API_ERROR")


def _action(payload: dict[str, Any]) -> str:
    action = str(payload.get("action") or "").strip().lower().replace("-", "_")
    if action:
        return action
    method = str(payload.get("_method") or payload.get("_actual_method") or "").upper()
    if method == "GET" and payload.get("card_id"):
        return "agent_status"
    if method == "GET" and payload.get("board_id"):
        return "get_board"
    if method == "GET":
        return "list_boards"
    if method == "PUT" and payload.get("board_id"):
        return "update_board"
    if method == "PUT" and payload.get("card_id"):
        return "update_card"
    if method == "PUT" and payload.get("column_id"):
        return "update_column"
    if method == "DELETE" and payload.get("card_id"):
        return "delete_card"
    if method == "DELETE" and payload.get("column_id"):
        return "delete_column"
    return "list_boards"


def _board_id(payload: dict[str, Any]) -> str:
    return str(payload.get("board_id") or payload.get("id") or "").strip()


def _card_id(payload: dict[str, Any]) -> str:
    return str(payload.get("card_id") or payload.get("id") or "").strip()


def _column_id(payload: dict[str, Any]) -> str:
    return str(payload.get("column_id") or payload.get("id") or "").strip()


def _invalid(message: str) -> dict[str, Any]:
    response = error(message, "INVALID_INPUT")
    response["_http_status"] = 400
    return response
