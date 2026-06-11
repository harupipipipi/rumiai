from __future__ import annotations

import re
import time
from typing import Any

from domain.tool.task_board import TaskBoardController


def _now_ms() -> int:
    return int(time.time() * 1000)


_STAGE_COLUMN_ALIASES = {
    "Doing": ("doing", "active", "in-progress", "inprogress", "working", "wip"),
    "Review": ("review", "qa-review", "qa", "code-review", "ready-for-review", "ready-review"),
    "Done": ("done", "completed", "complete", "closed", "applied", "merged"),
}


class TaskBoardAgentSessionController:
    """Link task board cards to defaultspack coding agent sessions."""

    def __init__(self, task_board: TaskBoardController | None = None) -> None:
        self._task_board = task_board or TaskBoardController()

    def run(self, arguments: dict[str, Any] | None = None, context: dict[str, Any] | None = None) -> dict[str, Any]:
        arguments = arguments or {}
        context = context or {}
        action = str(arguments.get("action") or "start").strip().lower()
        if action in {"start", "create", "run", "launch"}:
            return self._start(arguments, context)
        if action in {"status", "refresh"}:
            return self._status(arguments, context)
        if action in {"merge_report", "report", "ready"}:
            return self._merge_report(arguments, context)
        if action in {"mark_ready", "ready_for_review"}:
            return self._mark_ready(arguments, context)
        if action == "apply":
            return self._mark_terminal(arguments, context, terminal_state="applied", default_column="Done")
        if action in {"dismiss", "reject"}:
            return self._mark_terminal(arguments, context, terminal_state="dismissed", default_column=None)
        if action in {"unlink", "clear"}:
            return self._unlink(arguments, context)
        raise ValueError(f"Unsupported task_board agent session action: {action}")

    def _start(self, arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        card = self._card(arguments, context)
        task = _task_from_card(card, arguments)
        create_args = {
            "task": task,
            "agents": _agents(arguments),
            "orchestration": str(arguments.get("orchestration") or "round_robin"),
            "max_turns": int(arguments.get("max_turns") or 10),
            "worktree_mode": str(arguments.get("worktree_mode") or "metadata_only"),
        }
        for key in ("workspace_root", "workspace_id", "model"):
            if arguments.get(key) is not None:
                create_args[key] = arguments[key]
        from blocks.agent.coding_session_create import run as create_session

        session_context = dict(context)
        if not any(create_args.get(key) for key in ("workspace_root", "workspace_id")) and not session_context.get("workspace_root"):
            session_context.pop("conversation_workspace_dir", None)
        output = create_session(create_args, session_context)
        if output.get("status") != "ok":
            raise ValueError(_error_message(output, "coding session create failed"))
        data = output.get("data") if isinstance(output.get("data"), dict) else {}
        session_link = {
            "session_id": data.get("session_id"),
            "status": data.get("status") or "created",
            "task": task,
            "started_at": _now_ms(),
            "updated_at": _now_ms(),
            "workspace": data.get("workspace") if isinstance(data.get("workspace"), dict) else {},
            "agents": create_args["agents"],
            "ready_for_review": False,
            "terminal_state": "",
        }
        updated_card = self._update_card_session(
            card,
            context,
            session_link,
            column=_default_column(card, arguments, "Doing"),
            explicit_column=_has_explicit_column(arguments),
        )
        return self._result("start", updated_card, session_link, data)

    def _status(self, arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        card = self._card(arguments, context)
        session_link = self._session_link(card, arguments)
        session_id = str(session_link.get("session_id") or "").strip()
        if not session_id:
            raise ValueError("session_id not found on task board card")
        from blocks.agent.coding_session_status import run as session_status

        output = session_status({"session_id": session_id}, context)
        if output.get("status") != "ok":
            raise ValueError(_error_message(output, "coding session status failed"))
        data = output.get("data") if isinstance(output.get("data"), dict) else {}
        session_link = {
            **session_link,
            "status": str(data.get("status") or session_link.get("status") or ""),
            "updated_at": _now_ms(),
            "last_status": data,
        }
        updated_card = self._update_card_session(card, context, session_link)
        return self._result("status", updated_card, session_link, data)

    def _merge_report(self, arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        card = self._card(arguments, context)
        session_link = self._session_link(card, arguments)
        session_id = str(session_link.get("session_id") or "").strip()
        if not session_id:
            raise ValueError("session_id not found on task board card")
        from blocks.agent.coding_session_merge_report import run as merge_report

        output = merge_report({"session_id": session_id}, context)
        if output.get("status") != "ok":
            raise ValueError(_error_message(output, "coding session merge report failed"))
        data = output.get("data") if isinstance(output.get("data"), dict) else {}
        session_link = {
            **session_link,
            "status": "ready",
            "ready_for_review": True,
            "updated_at": _now_ms(),
            "merge_report": data.get("merge_report", data),
        }
        updated_card = self._update_card_session(
            card,
            context,
            session_link,
            column=_default_column(card, arguments, "Review"),
            explicit_column=_has_explicit_column(arguments),
        )
        return self._result("merge_report", updated_card, session_link, data)

    def _mark_ready(self, arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        card = self._card(arguments, context)
        session_link = {
            **self._session_link(card, arguments),
            "status": "ready",
            "ready_for_review": True,
            "updated_at": _now_ms(),
        }
        updated_card = self._update_card_session(
            card,
            context,
            session_link,
            column=_default_column(card, arguments, "Review"),
            explicit_column=_has_explicit_column(arguments),
        )
        return self._result("mark_ready", updated_card, session_link, {})

    def _mark_terminal(
        self,
        arguments: dict[str, Any],
        context: dict[str, Any],
        *,
        terminal_state: str,
        default_column: str | None,
    ) -> dict[str, Any]:
        card = self._card(arguments, context)
        session_link = {
            **self._session_link(card, arguments),
            "status": terminal_state,
            "ready_for_review": False,
            "terminal_state": terminal_state,
            terminal_state + "_at": _now_ms(),
            "updated_at": _now_ms(),
        }
        updated_card = self._update_card_session(
            card,
            context,
            session_link,
            column=_default_column(card, arguments, default_column) if default_column else None,
            explicit_column=_has_explicit_column(arguments),
        )
        return self._result(terminal_state, updated_card, session_link, {})

    def _unlink(self, arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        card = self._card(arguments, context)
        metadata = _metadata(card)
        previous = metadata.pop("agent_session", {})
        card = self._task_board.run(
            {"action": "update", "card_id": card["id"], "metadata": metadata},
            context,
        )["changed"]
        return self._result("unlink", card, {}, {"previous": previous})

    def _card(self, arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        card_id = str(arguments.get("card_id") or arguments.get("id") or "").strip()
        if not card_id:
            raise ValueError("card_id is required")
        board = self._task_board.run({"action": "list"}, context)
        for card in board.get("cards", []):
            if card.get("id") == card_id:
                return dict(card)
        raise ValueError("card_id not found")

    def _session_link(self, card: dict[str, Any], arguments: dict[str, Any]) -> dict[str, Any]:
        metadata = _metadata(card)
        link = dict(metadata.get("agent_session") if isinstance(metadata.get("agent_session"), dict) else {})
        if arguments.get("session_id"):
            link["session_id"] = str(arguments.get("session_id"))
        return link

    def _update_card_session(
        self,
        card: dict[str, Any],
        context: dict[str, Any],
        session_link: dict[str, Any],
        *,
        column: str | None = None,
        explicit_column: bool = False,
    ) -> dict[str, Any]:
        metadata = _metadata(card)
        metadata["agent_session"] = session_link
        history = list(metadata.get("agent_sessions") if isinstance(metadata.get("agent_sessions"), list) else [])
        session_id = session_link.get("session_id")
        if session_id and all(item.get("session_id") != session_id for item in history if isinstance(item, dict)):
            history.append({"session_id": session_id, "started_at": session_link.get("started_at")})
        if history:
            metadata["agent_sessions"] = history[-10:]
        update_args: dict[str, Any] = {
            "action": "update",
            "card_id": card["id"],
            "metadata": metadata,
        }
        target_column = self._resolve_target_column(card, context, column, explicit_column=explicit_column)
        if target_column:
            update_args["column"] = target_column
        updated = self._task_board.run(update_args, context)
        return dict(updated["changed"])

    def _resolve_target_column(
        self,
        card: dict[str, Any],
        context: dict[str, Any],
        column: str | None,
        *,
        explicit_column: bool,
    ) -> str | None:
        if not column:
            return None
        board = self._task_board.run({"action": "list"}, context)
        columns = list(board.get("columns") if isinstance(board.get("columns"), list) else [])
        exact = _find_column(columns, str(column))
        if exact is not None:
            return exact
        if explicit_column:
            raise ValueError(f"Unknown task board column: {column}")
        semantic = _find_stage_column(columns, str(column), current_column_id=str(card.get("column_id") or ""))
        if semantic is not None:
            return semantic
        return None

    @staticmethod
    def _result(action: str, card: dict[str, Any], session_link: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
        session_id = str(session_link.get("session_id") or "")
        summary = f"{action}: task board card {card.get('id')}"
        if session_id:
            summary += f" linked to {session_id}"
        return {
            "action": action,
            "summary": summary,
            "card": card,
            "session": data,
            "session_link": session_link,
        }


def tool_task_board_agent_session(arguments: dict[str, Any] | None = None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    result = TaskBoardAgentSessionController().run(arguments, context if isinstance(context, dict) else {})
    return {
        "result": result.get("summary", "task board agent session updated"),
        "is_error": False,
        "widget": {"type": "task_board_agent_session", **result},
    }


def _metadata(card: dict[str, Any]) -> dict[str, Any]:
    return dict(card.get("metadata") if isinstance(card.get("metadata"), dict) else {})


def _task_from_card(card: dict[str, Any], arguments: dict[str, Any]) -> str:
    explicit = str(arguments.get("task") or "").strip()
    if explicit:
        return explicit
    title = str(card.get("title") or "").strip()
    notes = str(card.get("notes") or "").strip()
    return title if not notes else f"{title}\n\nContext:\n{notes}"


def _agents(arguments: dict[str, Any]) -> list[dict[str, Any]]:
    agents = arguments.get("agents")
    if isinstance(agents, list) and agents:
        return [dict(agent) for agent in agents if isinstance(agent, dict)]
    model = str(arguments.get("model") or "stub/default")
    tools = list(arguments.get("tools") if isinstance(arguments.get("tools"), list) else [])
    return [{"name": "worker", "role": "coding worker", "model": model, "tools": tools}]


def _default_column(card: dict[str, Any], arguments: dict[str, Any], fallback_title: str | None) -> str | None:
    explicit = arguments.get("column") or arguments.get("column_id") or arguments.get("move_to")
    if explicit:
        return str(explicit)
    if fallback_title is None:
        return None
    return fallback_title


def _has_explicit_column(arguments: dict[str, Any]) -> bool:
    return any(arguments.get(key) for key in ("column", "column_id", "move_to"))


def _error_message(output: dict[str, Any], fallback: str) -> str:
    error = output.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or fallback)
    if isinstance(error, str) and error:
        return error
    return fallback


def _find_column(columns: list[dict[str, Any]], value: str) -> str | None:
    candidate = str(value).strip()
    if not candidate:
        return None
    normalized = _slugify(candidate)
    for column in columns:
        column_id = str(column.get("id") or "").strip()
        title = str(column.get("title") or "").strip()
        if candidate == column_id or candidate.lower() == title.lower():
            return column_id
        if normalized and (normalized == _slugify(column_id) or normalized == _slugify(title)):
            return column_id
    return None


def _find_stage_column(columns: list[dict[str, Any]], stage: str, *, current_column_id: str) -> str | None:
    current_column_id = str(current_column_id or "")
    stage_aliases = set(_STAGE_COLUMN_ALIASES.get(stage, ()))
    if stage == "Done":
        for column in columns:
            if bool(column.get("done")):
                return str(column.get("id") or "")
    for alias in stage_aliases:
        resolved = _find_column(columns, alias)
        if resolved is not None:
            return resolved
    if stage == "Done":
        return None
    current_position = 0
    for column in columns:
        if str(column.get("id") or "") == current_column_id:
            current_position = int(column.get("position") or 0)
            break
    for column in columns:
        column_id = str(column.get("id") or "")
        if column_id == current_column_id:
            continue
        if bool(column.get("done")):
            continue
        if int(column.get("position") or 0) > current_position:
            return column_id
    return None


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower())
    return slug.strip("-")
