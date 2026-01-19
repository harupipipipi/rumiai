from __future__ import annotations
from typing import Any, Dict

def run(context: Dict[str, Any]) -> None:
    ir = context.get("interface_registry")
    if not ir:
        return
    from chat_manager import ChatManager
    ir.register("service.chats", ChatManager(), meta={"component": "services_chats_v1"})
