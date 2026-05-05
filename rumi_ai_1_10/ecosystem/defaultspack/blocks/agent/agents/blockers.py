from blocks._common import error, ok
from domain.agent.blocker import BlockerStore


def run(input_data, context):
    del context
    input_data = input_data or {}
    method = str(input_data.get("_method") or input_data.get("method") or "GET").upper()
    store = BlockerStore()
    if method == "GET":
        return ok(
            {
                "blockers": store.list(
                    str(input_data.get("agent_id") or ""),
                    active_only=bool(input_data.get("active_only", False)),
                )
            }
        )
    if method == "POST":
        agent_id = str(input_data.get("agent_id") or "").strip()
        message = str(input_data.get("message") or "").strip()
        if not agent_id or not message:
            return error("agent_id and message are required", "INVALID_INPUT")
        return ok({"blocker": store.add(agent_id, message, severity=input_data.get("severity", "medium"))})
    if method in {"PUT", "PATCH"}:
        blocker_id = str(input_data.get("blocker_id") or input_data.get("id") or "").strip()
        resolved = store.resolve(blocker_id, resolution=input_data.get("resolution", ""))
        if resolved is None:
            return error("blocker not found", "NOT_FOUND")
        return ok({"blocker": resolved})
    return error("unsupported method", "METHOD_NOT_ALLOWED")
