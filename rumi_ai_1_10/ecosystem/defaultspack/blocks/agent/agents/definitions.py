import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from blocks._common import error, ok
from domain.agent.agent_store import AgentStore


def _agent_record(definition):
    if not isinstance(definition, dict):
        return {}
    model_policy = definition.get("model_policy") if isinstance(definition.get("model_policy"), dict) else {}
    api_key_policy = definition.get("api_key_policy") if isinstance(definition.get("api_key_policy"), dict) else {}
    tool_policy = definition.get("tool_policy") if isinstance(definition.get("tool_policy"), dict) else {}
    runtime_policy = definition.get("runtime_policy") if isinstance(definition.get("runtime_policy"), dict) else {}
    schedule_policy = definition.get("schedule_policy") if isinstance(definition.get("schedule_policy"), dict) else {}
    webhook_policy = definition.get("webhook_policy") if isinstance(definition.get("webhook_policy"), dict) else {}
    denylist = set(tool_policy.get("denylist") or [])
    schedule = {
        "enabled": schedule_policy.get("enabled", schedule_policy.get("type") not in {"manual", None}),
        "mode": runtime_policy.get("activation_mode") or schedule_policy.get("run_mode") or schedule_policy.get("type") or "manual",
        "interval_minutes": schedule_policy.get("every_minutes") or schedule_policy.get("interval_minutes"),
        "timezone": schedule_policy.get("timezone"),
        "start_now": schedule_policy.get("start_now"),
    }
    lifecycle = {
        "run_mode": runtime_policy.get("activation_mode") or schedule.get("mode"),
        "start_now": schedule.get("start_now"),
        "max_cost_usd": definition.get("stop_conditions", {}).get("max_cost_usd") if isinstance(definition.get("stop_conditions"), dict) else None,
        "approval_mode": tool_policy.get("approval_mode"),
    }
    return {
        "id": definition.get("agent_id"),
        "agent_id": definition.get("agent_id"),
        "name": definition.get("display_name") or definition.get("agent_id"),
        "display_name": definition.get("display_name"),
        "status": "idle",
        "profile_id": definition.get("profile_id"),
        "role": definition.get("role_key"),
        "system_prompt": definition.get("system_prompt"),
        "model": model_policy.get("default_model"),
        "api_key_id": api_key_policy.get("preferred_key_id"),
        "provider_id": api_key_policy.get("provider_id"),
        "browser_profile_id": tool_policy.get("browser_profile_id"),
        "browser_enabled": "browser_use" not in denylist,
        "computer_enabled": "computer_use" not in denylist,
        "tools": list(tool_policy.get("allowlist") or []),
        "tool_policy": {
            "allowed_tools": list(tool_policy.get("allowlist") or []),
            "denied_tools": list(tool_policy.get("denylist") or []),
            "browser_enabled": "browser_use" not in denylist,
            "computer_enabled": "computer_use" not in denylist,
            "require_approval_for": list(tool_policy.get("require_approval_for") or []),
        },
        "schedule": schedule,
        "lifecycle": lifecycle,
        "webhook": webhook_policy,
        "runtime_policy": runtime_policy,
        "schedule_policy": schedule_policy,
        "webhook_policy": webhook_policy,
        "created_at": definition.get("created_at"),
        "updated_at": definition.get("updated_at"),
    }


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
                return ok(_agent_record(agent))
            return ok({"agents": [_agent_record(agent) for agent in store.list()], "definitions": store.list(), "templates": store.templates()})
        if method == "POST":
            payload = input_data.get("definition") if isinstance(input_data.get("definition"), dict) else dict(input_data)
            agent = store.create_agent(payload)
            return ok(_agent_record(agent))
        if method in {"PUT", "PATCH"}:
            agent_id = str(input_data.get("agent_id") or input_data.get("id") or "").strip()
            if not agent_id:
                return error("agent_id is required", "INVALID_INPUT")
            updates = input_data.get("updates") if isinstance(input_data.get("updates"), dict) else dict(input_data)
            agent = store.update(agent_id, updates)
            if agent is None:
                return error("agent not found", "NOT_FOUND")
            return ok(_agent_record(agent))
        if method == "DELETE":
            agent_id = str(input_data.get("agent_id") or input_data.get("id") or "").strip()
            if not agent_id:
                return error("agent_id is required", "INVALID_INPUT")
            return ok({"deleted": store.delete(agent_id), "agent_id": agent_id})
    except Exception as exc:
        return error(str(exc), "AGENT_STORE_ERROR")
    return error("unsupported method", "METHOD_NOT_ALLOWED")
