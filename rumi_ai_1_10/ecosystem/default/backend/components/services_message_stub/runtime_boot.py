from __future__ import annotations

from typing import Any, Dict
import threading
import time

_ABORT = threading.Event()

def run(context: Dict[str, Any]) -> None:
    ir = context.get("interface_registry")
    if not ir:
        return

    def _chats():
        return ir.get("service.chats", strategy="last")

    def _append(chat_id: str, role: str, content: str, status: str = "completed") -> None:
        cm = _chats()
        from chat_manager import create_standard_message, add_message_to_history
        history = cm.load_chat_history(chat_id)
        msg = create_standard_message(
            role=role,
            content=content,
            parent_id=history.get("current_node"),
            status=status,
        )
        history = add_message_to_history(history, msg)
        cm.save_chat_history(chat_id, history)

    STUB = "AI subsystem is not installed yet. (prompt/ai_client/tool were removed; implement new services and rebind message.handle.)"

    def message_handle(chat_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        msg = (payload or {}).get("message") or {}
        text = msg.get("text", "") if isinstance(msg, dict) else ""
        if text.strip():
            _append(chat_id, "user", text)
        _append(chat_id, "assistant", STUB)
        return {"success": True, "response": STUB, "metadata": {"chat_id": chat_id}}

    def message_handle_stream(chat_id: str, payload: Dict[str, Any]):
        from flask import Response
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
                yield ch.replace('"', '\\"')
                time.sleep(0.003)
            yield '"}\n\n'
            yield 'data: {"type":"complete","full_text":"' + STUB.replace('"', '\\"') + '"}\n\n'

        _append(chat_id, "assistant", STUB)
        return Response(gen(), mimetype="text/event-stream")

    def message_abort() -> Dict[str, Any]:
        _ABORT.set()
        return {"success": True}

    ir.register("message.handle", message_handle, meta={"component": "services_message_stub_v1"})
    ir.register("message.handle_stream", message_handle_stream, meta={"component": "services_message_stub_v1"})
    ir.register("message.abort", message_abort, meta={"component": "services_message_stub_v1"})
