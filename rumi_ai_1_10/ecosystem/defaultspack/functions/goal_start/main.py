from __future__ import annotations

import sys
from pathlib import Path

PACK_ROOT = Path(__file__).resolve().parents[2]
RUMI_ROOT = PACK_ROOT.parents[1]
for path in (str(PACK_ROOT), str(RUMI_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from domain.goal.monitor import start_goal


def run(context, args):
    payload = args if isinstance(args, dict) else {}
    objective = str(payload.get("goal") or payload.get("objective") or "").strip()
    conversation_id = str(payload.get("conversation_id") or "").strip()
    if not objective:
        return {"status": "error", "error": {"code": "MISSING_ARGUMENT", "message": "goal is required"}}
    if not conversation_id:
        return {
            "status": "error",
            "error": {"code": "MISSING_ARGUMENT", "message": "conversation_id is required"},
        }
    return {
        "status": "ok",
        "data": start_goal(
            conversation_id=conversation_id,
            objective=objective,
            checker_policy=payload.get("checker_policy") if isinstance(payload.get("checker_policy"), dict) else {},
            metadata={"source": "slash_command", "request_id": (context or {}).get("request_id")},
        ),
    }
