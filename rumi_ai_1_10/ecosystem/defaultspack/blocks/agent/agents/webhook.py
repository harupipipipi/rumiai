from __future__ import annotations

from blocks._common import error, ok
from domain.agent.agent_runtime import AgentRuntime
from domain.agent.agent_store import AgentStore


def run(input_data, context=None):
    input_data = input_data or {}
    agent_id = str(input_data.get("agent_id") or input_data.get("id") or "").strip()
    if not agent_id:
        return error("agent_id is required", "INVALID_INPUT")
    definition = AgentStore().get(agent_id)
    if not definition:
        return error("agent not found", "NOT_FOUND")
    webhook_policy = definition.get("webhook_policy") if isinstance(definition.get("webhook_policy"), dict) else {}
    schedule_policy = definition.get("schedule_policy") if isinstance(definition.get("schedule_policy"), dict) else {}
    if not webhook_policy.get("enabled") and schedule_policy.get("type") != "webhook":
        return error("webhook is not enabled for this agent", "WEBHOOK_DISABLED")
    secret_error = _validate_secret(input_data, webhook_policy)
    if secret_error:
        return secret_error
    payload = input_data.get("payload") if isinstance(input_data.get("payload"), dict) else {}
    action = str(input_data.get("action") or payload.get("action") or "webhook").strip()
    message = str(input_data.get("message") or payload.get("message") or "").strip()
    if not message:
        message = "Webhook action received: " + action
    result = AgentRuntime().tick(
        agent_id,
        message=message,
        conversation_id=str(input_data.get("conversation_id") or ""),
        trigger="webhook",
        tools=input_data.get("tools") if isinstance(input_data.get("tools"), list) else None,
        tool_policy=input_data.get("tool_policy") if isinstance(input_data.get("tool_policy"), dict) else {},
        metadata={
            "source": "webhook",
            "webhook_action": action,
            "webhook_payload": payload,
        },
        context=context if isinstance(context, dict) else {},
    )
    if result.get("status") in {"error", "failed"}:
        return error(str(result.get("error") or "agent webhook tick failed"), "AGENT_WEBHOOK_FAILED")
    return ok({"accepted": True, "agent_id": agent_id, "action": action, "result": result})


def _validate_secret(input_data, webhook_policy):
    expected = str(webhook_policy.get("secret") or "").strip()
    if not expected:
        return None
    headers = input_data.get("_headers") if isinstance(input_data.get("_headers"), dict) else {}
    provided = str(
        input_data.get("secret")
        or input_data.get("token")
        or headers.get("X-Rumi-Webhook-Secret")
        or headers.get("x-rumi-webhook-secret")
        or ""
    ).strip()
    if provided != expected:
        return error("webhook secret is invalid", "WEBHOOK_AUTH_FAILED")
    return None
