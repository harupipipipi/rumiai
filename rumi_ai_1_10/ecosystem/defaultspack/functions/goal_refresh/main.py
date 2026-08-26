from __future__ import annotations

import sys
from pathlib import Path

PACK_ROOT = Path(__file__).resolve().parents[2]
RUMI_ROOT = PACK_ROOT.parents[1]
for path in (str(PACK_ROOT), str(RUMI_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from domain.goal.checker import run_goal_checker


def run(context, args):
    payload = args if isinstance(args, dict) else {}
    goal_run_id = str(payload.get("goal_run_id") or "").strip()
    if not goal_run_id:
        return {
            "status": "error",
            "error": {"code": "MISSING_ARGUMENT", "message": "goal_run_id is required"},
        }
    result = run_goal_checker(goal_run_id, context=context if isinstance(context, dict) else {})
    if isinstance(result, dict) and result.get("status") == "ok":
        return result
    return {
        "status": "error",
        "error": {
            "code": str((result or {}).get("code") or "GOAL_REFRESH_FAILED"),
            "message": str((result or {}).get("message") or "goal refresh failed"),
        },
    }
