import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import ok, error
from domain.agent.subagent_orchestrator import run_subagent_compat


def run(input_data, context):
    data = input_data if isinstance(input_data, dict) else {}
    role_id = str(data.get("role_id") or data.get("role") or "").strip()
    payload = data.get("payload") if isinstance(data.get("payload"), dict) else data
    if not role_id and isinstance(payload, dict) and any(payload.get(key) for key in ("task", "prompt")):
        role_id = "delegate"
    if not role_id:
        return error("role_id is required", "MISSING_PARAM")
    try:
        result = run_subagent_compat(
            role_id,
            payload,
            model=str(data.get("model") or ""),
            settings=data.get("settings") if isinstance(data.get("settings"), dict) else {},
            call_handler=(context or {}).get("call_handler") if isinstance(context, dict) else None,
            context=context if isinstance(context, dict) else {},
        )
        if isinstance(result, dict) and result.get("status") == "error":
            delegation_error = result.get("delegation_error") if isinstance(result.get("delegation_error"), dict) else {}
            code = str(delegation_error.get("code") or result.get("code") or "SUBAGENT_DELEGATION_FAILED")
            message = str(delegation_error.get("message") or result.get("error") or "subagent delegation failed")
            return {"status": "error", "error": {"code": code, "message": message, "details": result}}
        return ok(result)
    except ValueError as exc:
        return error(str(exc), "INVALID_SUBAGENT_ROLE")
