from __future__ import annotations

from typing import Any

from domain.ai_client.model_call import call_model
from domain.chat.tool_recommender import recommend_tool_ids
from domain.chat.tool_selection_schema import ToolRecommendation, ToolSelectionResult
from domain.tool.loading import split_tools_by_loading


class ToolSelectionOrchestrator:
    def __init__(self, *, call_handler: Any = None) -> None:
        self._call_handler = call_handler

    def select(
        self,
        user_text: str,
        tools: list[dict[str, Any]],
        *,
        limit: int = 8,
        selected_model_capabilities: dict[str, Any] | None = None,
        settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        allowed_tools = [tool for tool in tools if _tool_id(tool)]
        always_tools, vector_tools = split_tools_by_loading(allowed_tools)
        candidate_ids = recommend_tool_ids(user_text, vector_tools, limit=min(20, max(limit, 1)))
        candidates = [tool for tool in vector_tools if _tool_id(tool) in set(candidate_ids)]
        if not candidates and not always_tools:
            return ToolSelectionResult(candidate_count=0).to_dict()
        always_recommendations = [
            ToolRecommendation(tool_id=_tool_id(tool), confidence=1.0, reason="always-loaded tool")
            for tool in always_tools
            if _tool_id(tool)
        ]
        supports_tools = True
        if isinstance(selected_model_capabilities, dict) and "supports_tool_calling" in selected_model_capabilities:
            supports_tools = bool(selected_model_capabilities.get("supports_tool_calling"))
        if not candidates:
            return ToolSelectionResult(
                recommended_tools=always_recommendations[:limit],
                requires_tool_calling_model=bool(always_recommendations and supports_tools),
                candidate_count=len(always_tools),
                stage="tool_loading",
            ).to_dict()
        model_call = call_model(
            {
                "model_hint": (settings or {}).get("utility_models", {}).get("tool_selector") if isinstance((settings or {}).get("utility_models"), dict) else "",
                "question": (
                    "Select the minimum sufficient set of tools for the user message.\n"
                    "- Prefer read/search before write/execute.\n"
                    "- Never return a tool outside the supplied candidate list.\n"
                    "- Do not select a tool only because of word overlap.\n"
                    "- Do not select computer/browser-control tools without explicit user intent.\n"
                    "- Respect the maximum tool count.\n"
                    "Return JSON only with selected_tools as an array of {{tool_id, confidence, reason}}.\n\n"
                    "User message:\n{}\n\nCandidate tools:\n{}"
                ).format(
                    user_text,
                    str([_compact_tool(tool) for tool in candidates]),
                ),
                "output_schema": "tool_recommendation",
                "max_tokens": 800,
                "required_capabilities": ["model.fast"],
            },
            {"_model_call_depth": 0},
            call_handler=self._call_handler,
        )
        output = model_call.get("output") if isinstance(model_call, dict) and isinstance(model_call.get("output"), dict) else {}
        selected_ids = _selected_ids(output, candidate_ids[:limit])
        recommendations = [
            ToolRecommendation(tool_id=tool_id, confidence=_confidence(output, tool_id), reason=_reason(output, tool_id))
            for tool_id in selected_ids[:limit]
        ]
        recommendations = [*always_recommendations, *recommendations][:limit]
        return ToolSelectionResult(
            recommended_tools=recommendations,
            not_selected=[],
            requires_tool_calling_model=bool(recommendations and supports_tools),
            candidate_count=len(always_tools) + len(candidates),
            stage="utility_model" if isinstance(model_call, dict) and model_call.get("status") == "ok" else "keyword",
        ).to_dict()


def select_relevant_tools(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return ToolSelectionOrchestrator(call_handler=kwargs.pop("call_handler", None)).select(*args, **kwargs)


def _tool_id(tool: dict[str, Any]) -> str:
    return str(tool.get("tool_id") or tool.get("name") or "").strip()


def _compact_tool(tool: dict[str, Any]) -> dict[str, Any]:
    return {
        "tool_id": _tool_id(tool),
        "name": tool.get("name"),
        "summary": tool.get("summary") or tool.get("description"),
        "tags": tool.get("tags", []),
    }


def _selected_ids(output: Any, fallback: list[str]) -> list[str]:
    if not isinstance(output, dict):
        return fallback
    values = output.get("selected_tools")
    if not isinstance(values, list):
        values = output.get("recommended_tools")
    if not isinstance(values, list):
        return fallback
    ids = []
    for item in values:
        if isinstance(item, dict):
            tool_id = str(item.get("tool_id") or item.get("id") or "").strip()
        else:
            tool_id = str(item or "").strip()
        if tool_id and tool_id not in ids:
            ids.append(tool_id)
    return ids or fallback


def _confidence(output: Any, tool_id: str) -> float:
    items = _output_items(output)
    for item in items:
        if isinstance(item, dict) and str(item.get("tool_id") or "") == tool_id:
            try:
                return float(item.get("confidence", 0.6))
            except (TypeError, ValueError):
                return 0.6
    return 0.6


def _reason(output: Any, tool_id: str) -> str:
    items = _output_items(output)
    for item in items:
        if isinstance(item, dict) and str(item.get("tool_id") or "") == tool_id:
            return str(item.get("reason") or "selected by tool selector")
    return "selected by keyword prefilter"


def _output_items(output: Any) -> list[Any]:
    if not isinstance(output, dict):
        return []
    selected = output.get("selected_tools")
    if isinstance(selected, list):
        return selected
    recommended = output.get("recommended_tools")
    return recommended if isinstance(recommended, list) else []
