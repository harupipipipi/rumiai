from __future__ import annotations

from typing import Any

from .models import KanbanValidationError, gen_id
from .store import KanbanStore


class KanbanService:
    def __init__(self, store: KanbanStore | None = None) -> None:
        self.store = store or KanbanStore()

    def list_boards(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        scope_type, scope_id = _scope_from_payload(payload, required=False)
        if _truthy(payload.get("bootstrap")):
            if not scope_type or not scope_id:
                raise KanbanValidationError("scope_type and scope_id are required")
            return self.bootstrap_board({"scope_type": scope_type, "scope_id": scope_id, **payload})
        return {
            "boards": self.store.list_boards(scope_type=scope_type, scope_id=scope_id),
        }

    def bootstrap_board(self, payload: dict[str, Any]) -> dict[str, Any]:
        scope_type, scope_id = _scope_from_payload(payload, required=True)
        board = self.store.get_or_create_board(
            str(scope_type),
            str(scope_id),
            title=_optional_text(payload.get("title")),
        )
        self.store.ensure_default_columns(board["board_id"])
        return self.get_board(board["board_id"])

    def get_board(self, board_id: str) -> dict[str, Any]:
        if not board_id:
            raise KanbanValidationError("board_id is required")
        return self.store.board_snapshot(str(board_id))

    def update_board(self, board_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not board_id:
            raise KanbanValidationError("board_id is required")
        updates = _updates_from_payload(payload)
        self.store.update_board(str(board_id), updates)
        return self.get_board(str(board_id))

    def create_card(self, board_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not board_id:
            raise KanbanValidationError("board_id is required")
        return self.store.create_card(str(board_id), _without_control_keys(payload))

    def update_card(self, card_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not card_id:
            raise KanbanValidationError("card_id is required")
        return self.store.update_card(str(card_id), _updates_from_payload(payload))

    def delete_card(self, card_id: str) -> dict[str, Any]:
        if not card_id:
            raise KanbanValidationError("card_id is required")
        card = self.store.delete_card(str(card_id))
        return {"deleted": True, "card_id": card["card_id"], "card": card}

    def move_card(self, card_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not card_id:
            raise KanbanValidationError("card_id is required")
        card = self.store.move_card(str(card_id), _without_control_keys(payload))
        return self.get_board(card["board_id"])

    def create_column(self, board_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not board_id:
            raise KanbanValidationError("board_id is required")
        return self.store.create_column(
            str(board_id),
            str(payload.get("title") or ""),
            position=_optional_int(payload.get("position")),
            done=_optional_bool(payload.get("done")),
        )

    def update_column(self, column_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not column_id:
            raise KanbanValidationError("column_id is required")
        return self.store.update_column(str(column_id), _updates_from_payload(payload))

    def delete_column(self, column_id: str) -> dict[str, Any]:
        if not column_id:
            raise KanbanValidationError("column_id is required")
        column = self.store.delete_column(str(column_id))
        return {"deleted": True, "column_id": column["column_id"], "column": column}

    def sync_runs(self, board_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if not board_id:
            raise KanbanValidationError("board_id is required")
        payload = payload or {}
        self.store.add_event(str(board_id), "runs.sync.noop", {"source": payload.get("source") or "kanban_api"})
        return self.get_board(str(board_id))

    def agent_status(self, card_id: str) -> dict[str, Any]:
        if not card_id:
            raise KanbanValidationError("card_id is required")
        return self.store.require_card(str(card_id))

    def agent_start(self, card_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        card = self.store.require_card(str(card_id))
        updates = self._agent_updates(card, payload, "running", "started")
        if not updates.get("agent_run_id"):
            updates["agent_run_id"] = gen_id("krun_")
        if not updates.get("agent_session_id"):
            updates["agent_session_id"] = gen_id("ksess_")
        self.store.update_card(str(card_id), updates, event_type="agent.started")
        return self._move_card_to_column_title(str(card_id), "Doing", "agent.moved_to_doing")

    def agent_ready(self, card_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        card = self.store.require_card(str(card_id))
        self.store.update_card(
            str(card_id),
            self._agent_updates(card, payload or {}, "ready", "ready"),
            event_type="agent.ready",
        )
        return self._move_card_to_column_title(str(card_id), "Review", "agent.moved_to_review")

    def agent_apply(self, card_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        card = self.store.require_card(str(card_id))
        self.store.update_card(
            str(card_id),
            self._agent_updates(card, payload or {}, "applied", "applied"),
            event_type="agent.applied",
        )
        return self._move_card_to_column_title(str(card_id), "Done", "agent.moved_to_done")

    def agent_dismiss(self, card_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        card = self.store.require_card(str(card_id))
        self.store.update_card(
            str(card_id),
            self._agent_updates(card, payload or {}, "dismissed", "dismissed"),
            event_type="agent.dismissed",
        )
        return self._move_card_to_column_title(str(card_id), "Review", "agent.dismissed_to_review")

    def _move_card_to_column_title(self, card_id: str, title: str, event_type: str) -> dict[str, Any]:
        card = self.store.require_card(str(card_id))
        columns = self.store.list_columns(card["board_id"])
        target = next((column for column in columns if column["title"].lower() == title.lower()), None)
        if target is None:
            return card
        return self.store.move_card(
            str(card_id),
            {"column_id": target["column_id"]},
            event_type=event_type,
        )

    def _agent_updates(
        self,
        card: dict[str, Any],
        payload: dict[str, Any],
        status: str,
        action: str,
    ) -> dict[str, Any]:
        metadata = dict(card.get("metadata") or {})
        agent_meta = dict(metadata.get("agent") or {})
        agent_meta.update(
            {
                "last_action": action,
                "last_action_payload": _public_payload(payload),
            }
        )
        metadata["agent"] = agent_meta
        updates: dict[str, Any] = {
            "agent_status": status,
            "agent_run_id": payload.get("agent_run_id") or payload.get("run_id") or card.get("agent_run_id"),
            "agent_session_id": payload.get("agent_session_id") or payload.get("session_id") or card.get("agent_session_id"),
            "branch": payload.get("branch") or card.get("branch"),
            "pr_url": payload.get("pr_url") or card.get("pr_url"),
            "conversation_id": payload.get("conversation_id") or card.get("conversation_id"),
            "workspace_id": payload.get("workspace_id") or card.get("workspace_id"),
            "company_id": payload.get("company_id") or card.get("company_id"),
            "metadata": metadata,
        }
        return updates


def _scope_from_payload(payload: dict[str, Any], *, required: bool) -> tuple[str | None, str | None]:
    scope = payload.get("scope") if isinstance(payload.get("scope"), dict) else {}
    scope_type = (
        payload.get("scope_type")
        or payload.get("type")
        or scope.get("scope_type")
        or scope.get("type")
    )
    scope_id = (
        payload.get("scope_id")
        or payload.get("id")
        or scope.get("scope_id")
        or scope.get("id")
    )
    scope_type = str(scope_type).strip().lower() if scope_type is not None else None
    scope_id = str(scope_id).strip() if scope_id is not None else None
    if required and (not scope_type or not scope_id):
        raise KanbanValidationError("scope_type and scope_id are required")
    return scope_type or None, scope_id or None


def _updates_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    updates = payload.get("updates")
    if isinstance(updates, dict):
        return _without_control_keys(updates)
    return _without_control_keys(payload)


def _without_control_keys(payload: dict[str, Any]) -> dict[str, Any]:
    blocked = {
        "action",
        "board_id",
        "card_id",
        "column_id_path",
        "column_id_param",
        "_headers",
        "_handler",
        "_method",
        "_actual_method",
        "_raw_body",
        "_raw_body_base64",
    }
    return {
        str(key): value
        for key, value in (payload or {}).items()
        if not str(key).startswith("_") and str(key) not in blocked
    }


def _public_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in _without_control_keys(payload).items()
        if key not in {"metadata", "checklist"}
    }


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _optional_bool(value: Any) -> bool | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
