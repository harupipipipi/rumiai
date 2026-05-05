import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from blocks._common import error, ok
from domain.agent.agent_definition import AgentDefinition
from domain.agent.agent_store import AgentStore


def _definition_from_input(input_data):
    payload = dict(input_data or {})
    if "definition" in payload and isinstance(payload["definition"], dict):
        payload = dict(payload["definition"])
    return AgentDefinition.from_dict(payload)


def run(input_data, context):
    del context
    input_data = input_data or {}
    method = str(input_data.get("_method") or input_data.get("method") or "GET").upper()
    store = AgentStore()
    try:
        if method == "GET":
            agent_id = str(input_data.get("agent_id") or input_data.get("id") or "").strip()
            if agent_id:
                agent = store.get(agent_id)
                if agent is None:
                    return error("agent not found", "NOT_FOUND")
                return ok({"agent": agent})
            return ok({"agents": store.list()})
        if method == "POST":
            agent = store.upsert(_definition_from_input(input_data))
            return ok({"agent": agent})
        if method in {"PUT", "PATCH"}:
            agent_id = str(input_data.get("agent_id") or input_data.get("id") or "").strip()
            if not agent_id:
                return error("agent_id is required", "INVALID_INPUT")
            updates = input_data.get("updates") if isinstance(input_data.get("updates"), dict) else dict(input_data)
            agent = store.update(agent_id, updates)
            if agent is None:
                return error("agent not found", "NOT_FOUND")
            return ok({"agent": agent})
        if method == "DELETE":
            agent_id = str(input_data.get("agent_id") or input_data.get("id") or "").strip()
            if not agent_id:
                return error("agent_id is required", "INVALID_INPUT")
            return ok({"deleted": store.delete(agent_id), "agent_id": agent_id})
    except Exception as exc:
        return error(str(exc), "AGENT_STORE_ERROR")
    return error("unsupported method", "METHOD_NOT_ALLOWED")
