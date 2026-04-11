from __future__ import annotations

from typing import Any, Dict, List

from .chat_manager import ChatManager, Message
from .history import HistoryManager

_manager = ChatManager()


def create_conversation(title: str = "") -> Dict[str, Any]:
    conv = _manager.create(title=title)
    return {"created": True, "id": conv.chat_id, "title": conv.title}


def get_conversation(chat_id: str) -> Dict[str, Any]:
    conv = _manager.get_history(chat_id)
    if conv is None:
        return {"status_code": 404}
    return conv


def list_conversations() -> List[Dict[str, Any]]:
    return [conv.to_dict() for conv in _manager._conversations.values()]


def update_conversation(chat_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    conv = _manager.get_conversation(chat_id)
    if conv is None:
        return {"status_code": 404}
    if "title" in updates:
        conv.title = updates["title"]
    return {"updated": True, "id": chat_id}


def delete_conversation(chat_id: str) -> Dict[str, Any]:
    deleted = _manager._conversations.pop(chat_id, None) is not None
    return {"deleted": deleted}


def add_message(chat_id: str, role: str, content: Any) -> Dict[str, Any]:
    message = Message(role=role, content=content)
    _manager.add_message(chat_id, message)
    return message.to_dict()


def queue_message(chat_id: str, content: Any) -> Dict[str, Any]:
    message = Message(role="user", content=content)
    _manager.queue_message(chat_id, message)
    return message.to_dict()


def flush_queue(chat_id: str):
    return [msg.to_dict() for msg in _manager.flush_queue(chat_id)]


def stop_stream(chat_id: str) -> Dict[str, Any]:
    _manager.request_stop(chat_id)
    return {"stopped": True, "chat_id": chat_id}


def get_history(chat_id: str) -> Dict[str, Any]:
    history = _manager.get_history(chat_id)
    return history if history is not None else {"status_code": 404}


def summarize_and_trim(chat_id: str, keep_last: int = 20) -> Dict[str, Any]:
    history = _manager.get_history(chat_id)
    if history is None:
        return {"status_code": 404}
    messages = history.get("messages", [])
    trimmed = 0
    if len(messages) > keep_last + 1:
        head = [m for m in messages if m.get("role") == "system"][:1]
        tail = [m for m in messages if m.get("role") != "system"][-keep_last:]
        trimmed = len(messages) - len(head) - len(tail)
        history["messages"] = head + ([{"role": "system", "content": "summary"}] if trimmed > 0 else []) + tail
        conv = _manager.get_conversation(chat_id)
        if conv is not None:
            conv.messages = [Message(role=item.get("role", ""), content=item.get("content", "")) for item in history["messages"]]
    return {"trimmed": trimmed, "chat_id": chat_id}
