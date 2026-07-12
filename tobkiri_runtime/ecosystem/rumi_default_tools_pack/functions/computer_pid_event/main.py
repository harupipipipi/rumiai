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
        ComputerToolService,
        create_default_computer_tool_service,
    )
    from ecosystem.rumi_default_tools_pack.domain.computer.models import ComputerTarget
    from ecosystem.rumi_default_tools_pack.functions._computer_approval import (
        computer_action_approval_required,
        has_computer_action_approval,
    )
except ImportError:  # pragma: no cover - direct function execution fallback
    from domain.computer import ComputerToolService, create_default_computer_tool_service
    from domain.computer.models import ComputerTarget
    from functions._computer_approval import (
        computer_action_approval_required,
        has_computer_action_approval,
    )

_service: ComputerToolService | None = None


def _get_service() -> ComputerToolService:
    global _service
    if _service is None:
        _service = create_default_computer_tool_service()
    return _service


def run(context, args):
    try:
        a = args or {}
        action = a.get("action", "click")
        if not has_computer_action_approval(context, a, "computer.pid_event"):
            return computer_action_approval_required(a, "computer.pid_event")

        svc = _get_service()
        target = ComputerTarget(pid=a.get("pid"))

        payload = {
            key: value
            for key, value in a.items()
            if key not in {"action", "approval", "approval_token"}
        }
        result = svc.pid_event(action, target, payload)

        # Always mark as experimental
        if isinstance(result, dict):
            result["_experimental"] = True
            result.setdefault("notes", [])
            if isinstance(result["notes"], list):
                result["notes"].append("⚠️ EXPERIMENTAL: CGEventPostToPid")
        return result
    except Exception as e:
        return {"action": "computer.pid_event", "error": str(e), "_experimental": True}
