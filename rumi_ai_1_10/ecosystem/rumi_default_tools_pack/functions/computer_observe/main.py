from __future__ import annotations

import sys
from pathlib import Path

PACK_ROOT = Path(__file__).resolve().parents[2]
ECOSYSTEM_DIR = PACK_ROOT.parent
RUMI_ROOT = ECOSYSTEM_DIR.parent
DEFAULTSPACK_ROOT = ECOSYSTEM_DIR / "defaultspack"

for path in (RUMI_ROOT, PACK_ROOT, DEFAULTSPACK_ROOT):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)

try:
    from ecosystem.rumi_default_tools_pack.domain.computer import (
        ComputerSeatService,
        create_default_computer_seat_service,
    )
    from ecosystem.rumi_default_tools_pack.functions._computer_approval import (
        computer_action_approval_required,
        has_computer_action_approval,
    )
except ImportError:  # pragma: no cover - direct function execution fallback
    from domain.computer import ComputerSeatService, create_default_computer_seat_service
    from functions._computer_approval import (
        computer_action_approval_required,
        has_computer_action_approval,
    )

_service: ComputerSeatService | None = None


def _get_service() -> ComputerSeatService:
    global _service
    if _service is None:
        _service = create_default_computer_seat_service()
    return _service


def run(context, args):
    try:
        a = args or {}
        if not has_computer_action_approval(context, a, "computer.observe"):
            return computer_action_approval_required(a, "computer.observe")

        svc = _get_service()
        target = {
            "app": a.get("app"),
            "pid": a.get("pid"),
            "window_id": a.get("window_id"),
            "window_title": a.get("window_title"),
        }
        return svc.observe(target)
    except Exception as e:
        return {"action": "computer.observe", "error": str(e)}
