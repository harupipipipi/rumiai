from __future__ import annotations

import json
from typing import Any

from domain.ai_client.model_call import call_model
from domain.agent.subagent_roles import get_subagent_role


class SubagentOrchestrator:
    def __init__(self, *, call_handler: Any = None) -> None:
        self._call_handler = call_handler

    def run(
        self,
        role_id: str,
        payload: dict[str, Any] | None = None,
        *,
        model: str = "",
        settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        role = get_subagent_role(role_id)
        if role is None:
            raise ValueError("unknown subagent role: " + str(role_id))
        payload = payload if isinstance(payload, dict) else {}
        selected_model = model or _model_for_role(role_id, settings or {})
        output = self._run_with_model(role_id, payload, selected_model, role) if (selected_model or self._call_handler is not None) else None
        if output is None:
            output = self._deterministic_output(role_id, payload)
        return {
            "role_id": role_id,
            "model": selected_model,
            "role": role,
            "output": output,
            "events": [
                {
                    "type": "subagent_completed",
                    "role_id": role_id,
                    "model": selected_model,
                    "output_schema": role.get("output_schema"),
                }
            ],
        }

    def _run_with_model(self, role_id: str, payload: dict[str, Any], model: str, role: dict[str, Any]) -> dict[str, Any] | None:
        prompt = _prompt_for_role(role_id, payload, role)
        try:
            response = call_model(
                {
                    "model_hint": model,
                    "question": prompt,
                    "output_schema": role.get("output_schema"),
                    "max_tokens": role.get("max_tokens", 800),
                    "thinking_level": "none",
                    "required_capabilities": ["model.image_input"] if role_id == "vision_ocr" else [],
                },
                {"_model_call_depth": 0},
                call_handler=self._call_handler,
            )
        except Exception:
            return None
        if isinstance(response, dict) and response.get("status") == "ok":
            output = response.get("output")
            if isinstance(output, dict):
                return output
            parsed = _parse_json_response({"data": {"content": str(output or "")}})
            if parsed is not None:
                return parsed
        return None

    @staticmethod
    def _deterministic_output(role_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if role_id == "tool_selector":
            tools = payload.get("candidate_tools") if isinstance(payload.get("candidate_tools"), list) else []
            selected = []
            for tool in tools[:8]:
                if not isinstance(tool, dict):
                    continue
                tool_id = str(tool.get("tool_id") or tool.get("name") or "").strip()
                if tool_id:
                    selected.append({"tool_id": tool_id, "confidence": 0.55, "reason": "keyword prefilter candidate"})
            return {"recommended_tools": selected, "not_selected": [], "requires_tool_calling_model": bool(selected)}
        if role_id == "prompt_compactor":
            text = str(payload.get("prompt") or "")
            return {"original_chars": len(text), "compact_chars": len(text.strip()), "suggested_prompt": text.strip(), "risk": "low"}
        if role_id == "context_summarizer":
            return {"summary": str(payload.get("text") or "")[:1200], "source": "deterministic"}
        if role_id == "model_router":
            return {"reason_codes": ["deterministic_router"], "selected_model": payload.get("preferred_model", "")}
        if role_id == "vision_ocr":
            return {"summary": "画像添付あり", "uncertainties": ["subagent did not call a vision model"]}
        return {}


def run_subagent(role_id: str, payload: dict[str, Any] | None = None, *, model: str = "", settings: dict[str, Any] | None = None, call_handler: Any = None) -> dict[str, Any]:
    return SubagentOrchestrator(call_handler=call_handler).run(role_id, payload, model=model, settings=settings)


def run_subagent_compat(
    role_id: str,
    payload: dict[str, Any] | None = None,
    *,
    model: str = "",
    settings: dict[str, Any] | None = None,
    call_handler: Any = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cleaned_role_id = str(role_id or "").strip()
    cleaned_payload = payload if isinstance(payload, dict) else {}
    if get_subagent_role(cleaned_role_id) is not None:
        result = run_subagent(
            cleaned_role_id,
            cleaned_payload,
            model=model,
            settings=settings,
            call_handler=call_handler,
        )
        result["compatibility_alias"] = "subagent"
        result["route_kind"] = "utility_model_call"
        return result
    if cleaned_role_id in {"delegate", "agent_delegate", "task"} or str(cleaned_payload.get("task") or cleaned_payload.get("prompt") or "").strip():
        return _delegate_via_input(cleaned_role_id, cleaned_payload, model=model, context=context)
    raise ValueError("unknown subagent role: " + cleaned_role_id)


def _model_for_role(role_id: str, settings: dict[str, Any]) -> str:
    utility_models = settings.get("utility_models") if isinstance(settings.get("utility_models"), dict) else {}
    return str(utility_models.get(role_id) or utility_models.get("subagent_default") or "")


def _prompt_for_role(role_id: str, payload: dict[str, Any], role: dict[str, Any]) -> str:
    return (
        "You are a utility subagent. Return JSON only.\n"
        "role: {}\n"
        "schema: {}\n"
        "payload:\n{}"
    ).format(role_id, role.get("output_schema"), json.dumps(payload, ensure_ascii=False, indent=2)[:12000])


def _parse_json_response(response: Any) -> dict[str, Any] | None:
    data = response.get("data") if isinstance(response, dict) and response.get("status") == "ok" else response
    if isinstance(data, dict) and any(key in data for key in ("recommended_tools", "summary", "selected_model", "suggested_prompt")):
        return data
    content = data.get("content") if isinstance(data, dict) else None
    text = ""
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        text = "".join(str(block.get("text") or block) if isinstance(block, dict) else str(block) for block in content)
    if not text.strip():
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def extract_assistant_text_from_result(value: Any, *, _depth: int = 0) -> str:
    if _depth > 8:
        return ""
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return ""
        if text[:1] in {"{", "["}:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return text
            nested_text = extract_assistant_text_from_result(parsed, _depth=_depth + 1)
            return nested_text or text
        return text
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content") or item.get("raw_text")
                if text:
                    parts.append(str(text))
                    continue
            nested_text = extract_assistant_text_from_result(item, _depth=_depth + 1)
            if nested_text:
                parts.append(nested_text)
        return "\n".join(part.strip() for part in parts if part and part.strip()).strip()
    if not isinstance(value, dict):
        return ""

    for key in ("assistant_text", "raw_text", "output_text", "text", "answer", "summary", "message", "content"):
        if key not in value:
            continue
        text = extract_assistant_text_from_result(value.get(key), _depth=_depth + 1)
        if text:
            return text

    for key in ("data", "result", "output", "response"):
        if key not in value:
            continue
        text = extract_assistant_text_from_result(value.get(key), _depth=_depth + 1)
        if text:
            return text

    transport_keys = {
        "status",
        "execution_id",
        "delegate",
        "result",
        "data",
        "output",
        "response",
        "code",
        "error",
        "is_error",
        "error_type",
    }
    if _depth > 0 and value and not set(value).issubset(transport_keys):
        return json.dumps(value, ensure_ascii=False)
    return ""


def _delegate_via_input(
    role_id: str,
    payload: dict[str, Any],
    *,
    model: str = "",
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from domain.input.dispatcher import dispatch_input
    from domain.input.envelope import RumiInputEnvelope

    task = str(payload.get("task") or payload.get("prompt") or "").strip()
    if not task:
        raise ValueError("task is required for delegated compatibility alias")
    params = {
        "task": task,
        "tools": list(payload.get("tools") if isinstance(payload.get("tools"), list) else []),
        "model": str(payload.get("model") or model or ""),
        "system_prompt": payload.get("system_prompt"),
        "runtime_profile_key": payload.get("runtime_profile_key"),
        "capability_profile": payload.get("capability_profile"),
        "required_capabilities": payload.get("required_capabilities") or payload.get("capability"),
        "params": dict(payload.get("params") if isinstance(payload.get("params"), dict) else {}),
    }
    if "timeout_seconds" in payload:
        params["timeout_seconds"] = payload.get("timeout_seconds")
    result = dispatch_input(
        RumiInputEnvelope(
            role="user",
            input=task,
            chat={},
            source={"type": "compatibility", "provider": "subagent"},
            target=_delegate_target(payload, context or {}),
            delivery={"action_id": "agent.delegate"},
            attachments=list(payload.get("attachments") if isinstance(payload.get("attachments"), list) else []),
            metadata={"compatibility_alias": "subagent", "role_id": role_id},
            params=params,
            tools=list(payload.get("tools") if isinstance(payload.get("tools"), list) else []),
        ),
        context or {},
    )
    if isinstance(result, dict):
        assistant_text = extract_assistant_text_from_result(result)
        if assistant_text:
            result["assistant_text"] = assistant_text
        result.setdefault("compatibility_alias", "subagent")
        result.setdefault("route_kind", "agent.delegate")
    return result


def _delegate_target(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    target: dict[str, Any] = {}
    conversation_id = str(
        payload.get("conversation_id")
        or payload.get("target_conversation_id")
        or context.get("conversation_id")
        or ""
    ).strip()
    if conversation_id:
        target["conversation_id"] = conversation_id
    return target
