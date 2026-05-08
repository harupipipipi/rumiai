from __future__ import annotations

from typing import Any


def encode_ws_event(event: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {"type": "event", "event": event, "payload": payload}


def encode_ws_response(request_id: str, result: dict[str, Any]) -> dict[str, Any]:
    return {"type": "res", "id": request_id, "result": result}
