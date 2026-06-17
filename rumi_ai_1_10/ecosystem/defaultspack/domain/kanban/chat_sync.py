from __future__ import annotations

from typing import Any


def sync_conversation_kanban(conversation_id: str, *, reason: str = "chat_changed") -> dict[str, Any] | None:
    conversation_id = str(conversation_id or "").strip()
    if not conversation_id:
        return None
    try:
        from domain.chat.store import ChatStore
        from domain.kanban.service import KanbanService

        chat_store = ChatStore()
        conversation = chat_store.get_conversation(conversation_id)
        metadata = conversation.get("metadata") if isinstance(conversation, dict) and isinstance(conversation.get("metadata"), dict) else {}
        kanban = metadata.get("kanban") if isinstance(metadata.get("kanban"), dict) else {}
        board_id = str(kanban.get("board_id") or "").strip()
        if not board_id:
            return None
        last_extraction = kanban.get("last_extraction") if isinstance(kanban.get("last_extraction"), dict) else {}
        model = str(last_extraction.get("model") or conversation.get("model") or "").strip()
        use_ai = bool(model and str(last_extraction.get("source") or "").strip().lower() == "ai")
        return KanbanService().import_conversation(
            board_id,
            {
                "conversation_id": conversation_id,
                "title": conversation.get("title") if isinstance(conversation, dict) else "",
                "model": model,
                "use_ai": use_ai,
                "reason": reason,
            },
        )
    except Exception:
        return None
