from __future__ import annotations

import json
from typing import Any

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
        output = self._run_with_model(role_id, payload, selected_model, role) if selected_model else None
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
        if self._call_handler is None:
            return None
        prompt = _prompt_for_role(role_id, payload, role)
        try:
            response = self._call_handler(
                "defaults.ai.complete",
                {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "tools": [],
                    "params": {
                        "response_format": {"type": "json_object"},
                        "max_tokens": role.get("max_tokens", 800),
                        "thinking_level": "none",
                    },
                },
            )
        except Exception:
            return None
        return _parse_json_response(response)

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
