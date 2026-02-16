from __future__ import annotations
from typing import Any, Dict
import threading
import uuid
from datetime import datetime, timezone

_ABORT = threading.Event()


def _generate_message_id() -> str:
    return f"msg-{uuid.uuid4().hex[:12]}"


def _get_iso_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def run(context: Dict[str, Any]) -> None:
    ir = context.get("interface_registry")
    if not ir:
        return

    def _chats():
        return ir.get("service.chats", strategy="last")

    def _append(chat_id: str, role: str, content: str, status: str = "completed") -> None:
        cm = _chats()
        if cm is None:
            return
        try:
            history = cm.load_chat_history(chat_id)
        except FileNotFoundError:
            history = {
                "conversation_id": chat_id,
                "title": "新しいチャット",
                "created_at": _get_iso_timestamp(),
                "updated_at": _get_iso_timestamp(),
                "schema_version": "2.0",
                "current_node": None,
                "mapping": {},
                "messages": [],
                "is_pinned": False,
                "folder": None,
                "active_tools": None,
                "active_supporters": []
            }
        
        msg_id = _generate_message_id()
        parent_id = history.get("current_node")
        
        message = {
            "message_id": msg_id,
            "role": role,
            "content": content,
            "timestamp": _get_iso_timestamp(),
            "parent_id": parent_id,
            "children": [],
            "status": status
        }
        
        history["messages"].append(message)
        history["mapping"][msg_id] = {"id": msg_id, "parent": parent_id, "children": []}
        
        if parent_id and parent_id in history["mapping"]:
            if msg_id not in history["mapping"][parent_id]["children"]:
                history["mapping"][parent_id]["children"].append(msg_id)
        
        history["current_node"] = msg_id
        history["updated_at"] = _get_iso_timestamp()
        
        cm.save_chat_history(chat_id, history)

    STUB = "AI subsystem is not installed. Install ai_client/prompt/tool components to enable AI responses."

    def message_handle(chat_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        msg = (payload or {}).get("message") or {}
        text = msg.get("text", "") if isinstance(msg, dict) else ""
        if text.strip():
            _append(chat_id, "user", text)
        _append(chat_id, "assistant", STUB)
        return {"success": True, "response": STUB, "metadata": {"chat_id": chat_id}}

    def message_handle_stream(chat_id: str, payload: Dict[str, Any]):
        from flask import Response
        import time
        _ABORT.clear()

        msg = (payload or {}).get("message") or {}
        text = msg.get("text", "") if isinstance(msg, dict) else ""
        if text.strip():
            _append(chat_id, "user", text)

        def gen():
            yield 'data: {"type":"chunk","text":"'
            for ch in STUB:
                if _ABORT.is_set():
                    yield '"}\n\n'
                    return
                yield ch.replace('"', '\\"').replace('\n', '\\n')
                time.sleep(0.003)
            yield '"}\n\n'
            yield 'data: {"type":"complete","full_text":"' + STUB.replace('"', '\\"').replace('\n', '\\n') + '"}\n\n'

        _append(chat_id, "assistant", STUB)
        return Response(gen(), mimetype="text/event-stream")

    def message_abort() -> Dict[str, Any]:
        _ABORT.set()
        return {"success": True}

    ir.register("message.handle", message_handle, meta={"component": "services_message_stub_v1"})
    ir.register("message.handle_stream", message_handle_stream, meta={"component": "services_message_stub_v1"})
    ir.register("message.abort", message_abort, meta={"component": "services_message_stub_v1"})
