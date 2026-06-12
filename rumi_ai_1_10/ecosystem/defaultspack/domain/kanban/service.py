from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any

from .models import KanbanValidationError, gen_id
from .store import KanbanStore

KANBAN_SYSTEM_PROMPT_NOTE = (
    "この会話はKanbanに追加されています。会話内のタスク、期限、担当、優先度が変わった場合は、"
    "対応するKanbanカードを更新対象として扱ってください。"
)

_TASK_LINE_RE = re.compile(
    r"^\s*(?:[-*•]\s*(?:\[[ xX]\]\s*)?|(?:todo|task|action|next|fix|bug)\s*[:：]|(?:\d+|[a-zA-Z])[\.)]\s+)(.+)$",
    re.IGNORECASE,
)


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

    def import_conversation(self, board_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not board_id:
            raise KanbanValidationError("board_id is required")
        board = self.store.require_board(str(board_id))
        conversation_id = str(payload.get("conversation_id") or payload.get("source_id") or "").strip()
        if not conversation_id:
            raise KanbanValidationError("conversation_id is required")

        from domain.chat.store import ChatStore

        chat_store = ChatStore()
        conversation = chat_store.get_conversation(conversation_id)
        if conversation is None:
            from .models import KanbanNotFoundError

            raise KanbanNotFoundError("conversation not found: " + conversation_id)

        tasks, extraction = _conversation_tasks(conversation, payload)
        if not tasks:
            tasks = _fallback_conversation_tasks(conversation, payload)
            extraction = {"source": "fallback", "error": "empty AI task extraction"}

        existing_cards = [
            card
            for card in self.store.list_cards(board["board_id"])
            if str(card.get("conversation_id") or "") == conversation_id
            and str(card.get("source_type") or "") == "conversation"
        ]
        existing_cards.sort(
            key=lambda card: (
                int(((card.get("metadata") or {}).get("conversation_import") or {}).get("task_index") or 9999),
                int(card.get("created_at") or 0),
            )
        )

        saved_cards = []
        for index, task in enumerate(tasks[:8]):
            payload_card = _task_card_payload(
                board,
                conversation,
                task,
                index=index,
                extraction=extraction,
                request_payload=payload,
            )
            if index < len(existing_cards):
                saved_cards.append(self.store.update_card(existing_cards[index]["card_id"], payload_card, event_type="conversation.import.updated"))
            else:
                saved_cards.append(self.store.create_card(board["board_id"], payload_card))

        self.store.add_event(
            board["board_id"],
            "conversation.imported",
            {
                "conversation_id": conversation_id,
                "card_ids": [card["card_id"] for card in saved_cards],
                "task_count": len(saved_cards),
                "extraction": extraction,
            },
        )
        updated_conversation = _mark_conversation_in_kanban(
            chat_store,
            conversation,
            board=board,
            cards=saved_cards,
            extraction=extraction,
        )
        snapshot = self.get_board(board["board_id"])
        snapshot["imported"] = {
            "conversation_id": conversation_id,
            "card_ids": [card["card_id"] for card in saved_cards],
            "conversation": {
                "id": updated_conversation.get("id") if isinstance(updated_conversation, dict) else conversation_id,
                "title": updated_conversation.get("title") if isinstance(updated_conversation, dict) else conversation.get("title"),
                "metadata": updated_conversation.get("metadata") if isinstance(updated_conversation, dict) else conversation.get("metadata"),
            },
            "extraction": extraction,
        }
        return snapshot

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


def kanban_system_prompt_note(conv: dict[str, Any] | None) -> str:
    metadata = conv.get("metadata") if isinstance(conv, dict) and isinstance(conv.get("metadata"), dict) else {}
    kanban = metadata.get("kanban") if isinstance(metadata.get("kanban"), dict) else {}
    note = str(kanban.get("system_prompt_note") or "").strip()
    return note


def append_kanban_system_prompt_note(prompt: str, conv: dict[str, Any] | None) -> str:
    note = kanban_system_prompt_note(conv)
    if not note:
        return prompt
    prompt = str(prompt or "").strip()
    return f"{prompt}\n\n{note}" if prompt else note


def _conversation_tasks(conversation: dict[str, Any], payload: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    tasks = payload.get("tasks")
    if isinstance(tasks, list):
        normalized = [_normalize_task(item) for item in tasks]
        return [item for item in normalized if item], {"source": "provided"}
    if str(payload.get("use_ai", "true")).strip().lower() in {"0", "false", "no", "off"}:
        return _fallback_conversation_tasks(conversation, payload), {"source": "fallback", "reason": "ai_disabled"}
    model = str(payload.get("model") or payload.get("model_id") or "").strip()
    if not model:
        return _fallback_conversation_tasks(conversation, payload), {"source": "fallback", "reason": "model_missing"}
    authority_context = payload.get("_authority_context") if isinstance(payload.get("_authority_context"), dict) else {}
    if not authority_context:
        return _fallback_conversation_tasks(conversation, payload), {
            "source": "fallback",
            "model": model,
            "reason": "authority_context_missing",
        }
    try:
        messages = [
            {
                "role": "system",
                "content": (
                    "Extract a concise Kanban task list from the conversation. "
                    "Return only JSON with key tasks. Each task must include title, description, priority, labels, and checklist."
                ),
            },
            {"role": "user", "content": _conversation_excerpt(conversation, limit=9000)},
        ]
        params = {
            "temperature": 0,
            "max_tokens": 900,
            "_authority_context": authority_context,
        }
        response = _complete_with_timeout(
            model,
            messages,
            params=params,
            timeout_seconds=_ai_extract_timeout_seconds(payload),
        )
        text = _response_text(response)
        parsed_tasks = _parse_task_json(text)
        if parsed_tasks:
            return parsed_tasks, {"source": "ai", "model": model}
        return _fallback_conversation_tasks(conversation, payload), {"source": "fallback", "model": model, "reason": "ai_json_empty"}
    except Exception as exc:
        return _fallback_conversation_tasks(conversation, payload), {"source": "fallback", "model": model, "error": str(exc)}


def _complete_with_timeout(
    model: str,
    messages: list[dict[str, Any]],
    *,
    params: dict[str, Any],
    timeout_seconds: float,
) -> Any:
    from domain.ai_client.client import AIClient

    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="kanban-ai-extract")
    future = executor.submit(AIClient().complete, model, messages, [], params)
    try:
        return future.result(timeout=timeout_seconds)
    except FutureTimeoutError as exc:
        raise TimeoutError(f"AI task extraction timed out after {timeout_seconds:g}s") from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _ai_extract_timeout_seconds(payload: dict[str, Any]) -> float:
    raw = payload.get("ai_timeout_seconds") or os.environ.get("RUMI_KANBAN_AI_EXTRACT_TIMEOUT_SECONDS") or "8"
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = 8.0
    return max(0.05, min(20.0, value))


def _fallback_conversation_tasks(conversation: dict[str, Any], payload: dict[str, Any]) -> list[dict[str, Any]]:
    title = str(payload.get("title") or conversation.get("title") or "Conversation task").strip()
    lines = _task_like_lines(conversation)
    if lines:
        tasks = []
        for line in lines[:6]:
            tasks.append(
                {
                    "title": _compact_text(line, 96),
                    "description": "Imported from conversation: " + title,
                    "priority": "normal",
                    "labels": ["conversation"],
                    "checklist": [],
                }
            )
        return tasks
    excerpt = _conversation_excerpt(conversation, limit=1200)
    return [
        {
            "title": _compact_text(title if title != "New Conversation" else "Review conversation tasks", 96),
            "description": _compact_text(excerpt, 800),
            "priority": "normal",
            "labels": ["conversation"],
            "checklist": _fallback_checklist(conversation),
        }
    ]


def _task_card_payload(
    board: dict[str, Any],
    conversation: dict[str, Any],
    task: dict[str, Any],
    *,
    index: int,
    extraction: dict[str, Any],
    request_payload: dict[str, Any],
) -> dict[str, Any]:
    metadata = {
        "conversation_import": {
            "task_index": index,
            "conversation_title": conversation.get("title"),
            "conversation_group_id": conversation.get("group_id") or (conversation.get("metadata") or {}).get("group_id"),
            "board_scope_type": board.get("scope_type"),
            "board_scope_id": board.get("scope_id"),
            "extraction": extraction,
        },
        "conversation_title": conversation.get("title"),
        "conversation_group_id": conversation.get("group_id") or (conversation.get("metadata") or {}).get("group_id"),
    }
    column = str(request_payload.get("column_id") or request_payload.get("column") or "").strip()
    return {
        "title": task.get("title") or conversation.get("title") or "Conversation task",
        "description": task.get("description"),
        "priority": task.get("priority") or "normal",
        "labels": task.get("labels") or ["conversation"],
        "checklist": task.get("checklist") or [],
        "source_type": "conversation",
        "source_id": "{}:{}".format(conversation.get("id"), index),
        "conversation_id": conversation.get("id"),
        "workspace_id": request_payload.get("workspace_id") or (conversation.get("metadata") or {}).get("workspace_id"),
        "company_id": request_payload.get("company_id") or (conversation.get("metadata") or {}).get("company_id"),
        "column_id": column or None,
        "metadata": metadata,
    }


def _mark_conversation_in_kanban(
    chat_store: Any,
    conversation: dict[str, Any],
    *,
    board: dict[str, Any],
    cards: list[dict[str, Any]],
    extraction: dict[str, Any],
) -> dict[str, Any]:
    metadata = dict(conversation.get("metadata") or {})
    existing = metadata.get("kanban") if isinstance(metadata.get("kanban"), dict) else {}
    boards = list(existing.get("boards") or []) if isinstance(existing.get("boards"), list) else []
    board_entry = {
        "board_id": board.get("board_id"),
        "scope_type": board.get("scope_type"),
        "scope_id": board.get("scope_id"),
        "card_ids": [card.get("card_id") for card in cards],
    }
    boards = [item for item in boards if not isinstance(item, dict) or item.get("board_id") != board.get("board_id")]
    boards.append(board_entry)
    metadata["kanban"] = {
        **existing,
        "added": True,
        "board_id": board.get("board_id"),
        "card_ids": [card.get("card_id") for card in cards],
        "boards": boards[-12:],
        "last_extraction": extraction,
        "system_prompt_note": KANBAN_SYSTEM_PROMPT_NOTE,
    }
    return chat_store.update_conversation(str(conversation.get("id") or ""), {"metadata": metadata}) or conversation


def _normalize_task(item: Any) -> dict[str, Any] | None:
    if isinstance(item, str):
        title = item.strip()
        return {"title": title, "description": "", "priority": "normal", "labels": ["conversation"], "checklist": []} if title else None
    if not isinstance(item, dict):
        return None
    title = str(item.get("title") or item.get("name") or "").strip()
    if not title:
        return None
    return {
        "title": _compact_text(title, 120),
        "description": _compact_text(str(item.get("description") or item.get("notes") or ""), 1200),
        "priority": _priority(item.get("priority")),
        "labels": [str(label).strip() for label in item.get("labels", []) if str(label).strip()] if isinstance(item.get("labels"), list) else ["conversation"],
        "checklist": _normalize_checklist(item.get("checklist")),
    }


def _normalize_checklist(value: Any) -> list[dict[str, Any]]:
    items = value if isinstance(value, list) else []
    result = []
    for index, item in enumerate(items[:12]):
        if isinstance(item, dict):
            title = str(item.get("title") or item.get("text") or "").strip()
            done = bool(item.get("done") or item.get("checked"))
        else:
            title = str(item).strip()
            done = False
        if title:
            result.append({"id": "import-{}".format(index + 1), "title": _compact_text(title, 140), "done": done})
    return result


def _priority(value: Any) -> str:
    normalized = str(value or "normal").strip().lower()
    if normalized in {"urgent", "high", "normal", "low"}:
        return normalized
    return "normal"


def _response_text(response: Any) -> str:
    if isinstance(response, str):
        return response
    if not isinstance(response, dict):
        return ""
    if isinstance(response.get("text"), str):
        return str(response.get("text"))
    content = response.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
            else:
                parts.append(str(item))
        return "\n".join(part for part in parts if part)
    return str(response.get("message") or "")


def _parse_task_json(text: str) -> list[dict[str, Any]]:
    text = str(text or "").strip()
    if not text:
        return []
    candidates = [text]
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        candidates.insert(0, fenced.group(1).strip())
    bracket = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if bracket:
        candidates.append(bracket.group(1).strip())
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        raw_tasks = parsed.get("tasks") if isinstance(parsed, dict) else parsed
        if isinstance(raw_tasks, list):
            normalized = [_normalize_task(item) for item in raw_tasks]
            return [item for item in normalized if item]
    return []


def _conversation_excerpt(conversation: dict[str, Any], *, limit: int) -> str:
    messages = conversation.get("messages") if isinstance(conversation.get("messages"), list) else []
    parts = ["Title: " + str(conversation.get("title") or "")]
    for message in messages[-30:]:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "message")
        raw = str(message.get("raw_text") or _content_text(message.get("content")) or "").strip()
        if raw:
            parts.append("{}: {}".format(role, raw))
    text = "\n".join(parts).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _task_like_lines(conversation: dict[str, Any]) -> list[str]:
    lines = []
    for raw_line in _conversation_excerpt(conversation, limit=9000).splitlines():
        line = re.sub(r"^\s*(?:user|assistant|system|tool)\s*:\s*", "", raw_line, flags=re.IGNORECASE)
        match = _TASK_LINE_RE.match(line)
        if match:
            task_line = match.group(1).strip()
            if task_line:
                lines.append(task_line)
    return lines


def _fallback_checklist(conversation: dict[str, Any]) -> list[dict[str, Any]]:
    lines = _task_like_lines(conversation)
    return [{"id": "import-{}".format(index + 1), "title": _compact_text(line, 120), "done": False} for index, line in enumerate(lines[:8])]


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for item in content:
        if isinstance(item, dict):
            parts.append(str(item.get("text") or item.get("content") or ""))
    return "\n".join(part for part in parts if part)


def _compact_text(value: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"
