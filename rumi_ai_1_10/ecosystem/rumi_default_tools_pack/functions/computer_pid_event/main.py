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
    from ecosystem.rumi_default_tools_pack.domain.computer.models import ComputerTarget
    from ecosystem.rumi_default_tools_pack.functions._computer_approval import (
        computer_action_approval_required,
        has_computer_action_approval,
    )
except ImportError:  # pragma: no cover - direct function execution fallback
    from domain.computer import ComputerSeatService, create_default_computer_seat_service
    from domain.computer.models import ComputerTarget
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
        action = a.get("action", "click")
        if not has_computer_action_approval(context, a, "computer.pid_event"):
            return computer_action_approval_required(a, "computer.pid_event")

        svc = _get_service()
        target = ComputerTarget(pid=a.get("pid"))

        if action == "click":
            result = svc.click(target, x=a.get("x", 0), y=a.get("y", 0), button=a.get("button", "left"))
        elif action == "type_text":
            result = svc.type_text(target, text=a.get("text", ""))
        elif action == "key":
            result = svc.key(target, key_combo=a.get("key_combo", ""))
        elif action == "scroll":
            result = svc.scroll(target, x=a.get("x", 0), y=a.get("y", 0), direction=a.get("direction", "down"), clicks=a.get("clicks", 3))
        else:
            result = {"action": action, "error": f"Unknown action: {action}"}

        # Always mark as experimental
        if isinstance(result, dict):
            result["_experimental"] = True
            result.setdefault("notes", [])
            if isinstance(result["notes"], list):
                result["notes"].append("⚠️ EXPERIMENTAL: CGEventPostToPid")
        return result
    except Exception as e:
        return {"action": "computer.pid_event", "error": str(e), "_experimental": True}
