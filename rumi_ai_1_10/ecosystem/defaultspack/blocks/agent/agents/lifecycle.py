from __future__ import annotations

from ._common import AgentRuntime, agent_error, ok


def run(input_data, context=None):
    try:
        runtime = AgentRuntime()
        agent_id = str(input_data.get("agent_id") or input_data.get("id") or "")
        action = str(input_data.get("action") or "").lower()
        payload = input_data.get("payload") if isinstance(input_data.get("payload"), dict) else {}
        if action == "start":
            return ok(runtime.start(agent_id))
        if action == "pause":
            return ok(runtime.pause(agent_id))
        if action == "resume":
            return ok(runtime.resume(agent_id))
        if action == "stop":
            return ok(runtime.stop(agent_id))
        if action == "tick":
            return ok(runtime.tick(agent_id, message=str(payload.get("message") or input_data.get("message") or "")))
        raise ValueError("unsupported lifecycle action")
    except Exception as exc:
        return agent_error(exc)
