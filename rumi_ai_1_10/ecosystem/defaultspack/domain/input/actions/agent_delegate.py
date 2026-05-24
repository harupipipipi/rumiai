from __future__ import annotations

from typing import Any

from domain.input.envelope import RumiInputEnvelope


def handle(envelope: RumiInputEnvelope, context: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = _delegate_payload(envelope)
    task = str(payload.get("task") or payload.get("prompt") or envelope.input or "").strip()
    if not task:
        return {"status": "error", "code": "MISSING_INPUT", "error": "task is required", "assistant_text": ""}
    from blocks.agent.execute import run as execute_agent

    result = execute_agent(
        {
            "task": task,
            "tools": list(payload.get("tools") if isinstance(payload.get("tools"), list) else envelope.tools),
            "model": str(payload.get("model") or payload.get("profile_id") or payload.get("preferred_model") or ""),
            "system_prompt": payload.get("system_prompt"),
            "runtime_profile_key": payload.get("runtime_profile_key"),
            "capability_profile": payload.get("capability_profile"),
            "required_capabilities": payload.get("required_capabilities") or payload.get("capability"),
            "params": dict(payload.get("params") if isinstance(payload.get("params"), dict) else {}),
            "attachments": list(payload.get("attachments") if isinstance(payload.get("attachments"), list) else envelope.attachments),
            "target": dict(envelope.target if isinstance(envelope.target, dict) else {}),
            "delivery": dict(envelope.delivery if isinstance(envelope.delivery, dict) else {}),
        },
        _delegate_context(envelope, context or {}),
    )
    if isinstance(result, dict) and result.get("status") == "ok":
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        return {
            "status": "ok",
            "assistant_text": "",
            "delegate": {
                "execution_id": data.get("execution_id"),
                "status": data.get("status"),
                "required_capabilities": payload.get("required_capabilities") or payload.get("capability"),
                "tools": payload.get("tools") if isinstance(payload.get("tools"), list) else envelope.tools,
            },
            "result": data,
        }
    error_data = result.get("error") if isinstance(result, dict) and isinstance(result.get("error"), dict) else {}
    return {
        "status": "error",
        "assistant_text": "",
        "code": str(error_data.get("code") or "INPUT_ACTION_FAILED"),
        "error": str(error_data.get("message") or "agent delegation failed"),
    }


def _delegate_payload(envelope: RumiInputEnvelope) -> dict[str, Any]:
    payload = envelope.params.get("delegate") if isinstance(envelope.params.get("delegate"), dict) else {}
    if payload:
        return dict(payload)
    return dict(envelope.params if isinstance(envelope.params, dict) else {})


def _delegate_context(envelope: RumiInputEnvelope, context: dict[str, Any]) -> dict[str, Any]:
    updated = dict(context or {})
    target = envelope.target if isinstance(envelope.target, dict) else {}
    if target.get("conversation_id"):
        updated.setdefault("conversation_id", str(target.get("conversation_id")))
    if isinstance(envelope.metadata, dict) and envelope.metadata:
        updated.setdefault("delegate_metadata", dict(envelope.metadata))
    payload = _delegate_payload(envelope)
    if target:
        updated.setdefault("target", dict(target))
    if isinstance(envelope.delivery, dict) and envelope.delivery:
        updated.setdefault("delivery", dict(envelope.delivery))
    if isinstance(envelope.attachments, list) and envelope.attachments:
        updated.setdefault("attachments", list(envelope.attachments))
    required_capabilities = (
        payload.get("required_capabilities")
        or payload.get("capability")
        or envelope.params.get("required_capabilities")
        or envelope.params.get("capability")
    )
    if required_capabilities:
        updated.setdefault("required_capabilities", required_capabilities)
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    if params:
        updated.setdefault("params", dict(params))
    return updated
