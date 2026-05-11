from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from domain.computer import ComputerSeatService, DriverRegistry

_service: ComputerSeatService | None = None


def _get_service() -> ComputerSeatService:
    global _service
    if _service is None:
        _service = ComputerSeatService(DriverRegistry())
    return _service


def run(context, args):
    try:
        svc = _get_service()
        a = args or {}
        target = {
            "app": a.get("app"),
            "pid": a.get("pid"),
            "window_id": a.get("window_id"),
        }
        element_or_point = None
        if a.get("element_id"):
            element_or_point = {"id": a["element_id"]}
        elif a.get("point"):
            element_or_point = tuple(a["point"])
        return svc.semantic_action(
            target, intent=a.get("intent", ""), element_or_point=element_or_point
        )
    except Exception as e:
        return {"action": "computer.semantic_action", "error": str(e)}
