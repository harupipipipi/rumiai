from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from domain.computer import ComputerToolService, create_default_computer_tool_service

_service: ComputerToolService | None = None


def _get_service() -> ComputerToolService:
    global _service
    if _service is None:
        _service = create_default_computer_tool_service()
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
