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
        target = {
            "app": (args or {}).get("app"),
            "pid": (args or {}).get("pid"),
            "window_id": (args or {}).get("window_id"),
            "window_title": (args or {}).get("window_title"),
        }
        return svc.observe(target)
    except Exception as e:
        return {"action": "computer.observe", "error": str(e)}
