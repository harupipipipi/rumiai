from __future__ import annotations

from typing import Any

from domain.input.envelope import RumiInputEnvelope


_FAILED_DELEGATE_STATUSES = {"error", "failed", "failure"}
_PROVIDER_ERROR_HINTS = (
    "provider error",
    "provider is not configured",
    "model provider",
    "llm provider",
)


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
            "timeout_seconds": payload.get("timeout_seconds"),
        },
        _delegate_context(envelope, context or {}),
    )
    if isinstance(result, dict) and result.get("status") == "ok":
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        delegate = _delegate_summary(data, payload, envelope)
        if _delegate_failed(data):
            code, assistant_text = _delegate_failure_summary(data)
            delegate["code"] = code
            delegate["error"] = assistant_text
            return {
                "status": "error",
                "assistant_text": assistant_text,
                "code": code,
                "error": assistant_text,
                "delegate": delegate,
                "result": _safe_failed_delegate_result(data, assistant_text, code),
            }
        return {
            "status": "ok",
            "assistant_text": "",
            "delegate": delegate,
            "result": data,
        }
    error_data = result.get("error") if isinstance(result, dict) and isinstance(result.get("error"), dict) else {}
    assistant_text = "The delegated agent could not start."
    return {
        "status": "error",
        "assistant_text": assistant_text,
        "code": str(error_data.get("code") or "INPUT_ACTION_FAILED"),
        "error": assistant_text,
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


def _delegate_summary(data: dict[str, Any], payload: dict[str, Any], envelope: RumiInputEnvelope) -> dict[str, Any]:
    return {
        "execution_id": data.get("execution_id"),
        "status": data.get("status"),
        "required_capabilities": payload.get("required_capabilities") or payload.get("capability"),
        "tools": payload.get("tools") if isinstance(payload.get("tools"), list) else envelope.tools,
    }


def _delegate_failed(data: dict[str, Any]) -> bool:
    status = str(data.get("status") or "").strip().lower()
    if status in _FAILED_DELEGATE_STATUSES:
        return True
    nested = data.get("result") if isinstance(data.get("result"), dict) else {}
    nested_status = str(nested.get("status") or "").strip().lower()
    return nested_status in _FAILED_DELEGATE_STATUSES


def _delegate_failure_summary(data: dict[str, Any]) -> tuple[str, str]:
    if _contains_provider_error_hint(data):
        return (
            "DELEGATE_PROVIDER_ERROR",
            "The delegated agent could not complete because the model provider returned an error.",
        )
    return (
        "DELEGATE_RUN_FAILED",
        "The delegated agent could not complete before producing a response.",
    )


def _safe_failed_delegate_result(data: dict[str, Any], assistant_text: str, code: str) -> dict[str, Any]:
    safe: dict[str, Any] = {
        "status": str(data.get("status") or "error"),
        "code": code,
        "error": assistant_text,
        "error_redacted": True,
    }
    execution_id = _execution_id_from_delegate_data(data)
    if execution_id:
        safe["execution_id"] = execution_id
    return safe


def _execution_id_from_delegate_data(data: dict[str, Any]) -> str:
    execution_id = str(data.get("execution_id") or "").strip()
    if execution_id:
        return execution_id
    nested = data.get("result") if isinstance(data.get("result"), dict) else {}
    return str(nested.get("execution_id") or "").strip()


def _contains_provider_error_hint(value: Any, *, depth: int = 0) -> bool:
    if depth > 4:
        return False
    if isinstance(value, str):
        lowered = value.lower()
        return any(hint in lowered for hint in _PROVIDER_ERROR_HINTS)
    if isinstance(value, dict):
        return any(_contains_provider_error_hint(item, depth=depth + 1) for item in value.values())
    if isinstance(value, list):
        return any(_contains_provider_error_hint(item, depth=depth + 1) for item in value[:20])
    return False
