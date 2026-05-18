import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import ok, error
from domain.agent.subagent_orchestrator import run_subagent


def run(input_data, context):
    data = input_data if isinstance(input_data, dict) else {}
    role_id = str(data.get("role_id") or data.get("role") or "").strip()
    if not role_id:
        return error("role_id is required", "MISSING_PARAM")
    return ok(
        run_subagent(
            role_id,
            data.get("payload") if isinstance(data.get("payload"), dict) else data,
            model=str(data.get("model") or ""),
            settings=data.get("settings") if isinstance(data.get("settings"), dict) else {},
            call_handler=(context or {}).get("call_handler") if isinstance(context, dict) else None,
        )
    )
