from __future__ import annotations

from typing import Any

from domain.agent.subagent_orchestrator import run_subagent
from domain.chat.tool_recommender import recommend_tool_ids
from domain.chat.tool_selection_schema import COMPUTER_TOOL_IDS, ToolRecommendation, ToolSelectionResult


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
        allowed_tools = [tool for tool in tools if _tool_id(tool) not in COMPUTER_TOOL_IDS]
        candidate_ids = recommend_tool_ids(user_text, allowed_tools, limit=min(20, max(limit, 1)))
        candidates = [tool for tool in allowed_tools if _tool_id(tool) in set(candidate_ids)]
        if not candidates:
            return ToolSelectionResult(candidate_count=0).to_dict()
        subagent = run_subagent(
            "tool_selector",
            {"user_text": user_text, "candidate_tools": [_compact_tool(tool) for tool in candidates]},
            settings=settings,
            call_handler=self._call_handler,
        )
        output = subagent.get("output") if isinstance(subagent, dict) else {}
        selected_ids = _selected_ids(output, candidate_ids[:limit])
        recommendations = [
            ToolRecommendation(tool_id=tool_id, confidence=_confidence(output, tool_id), reason=_reason(output, tool_id))
            for tool_id in selected_ids[:limit]
        ]
        supports_tools = True
        if isinstance(selected_model_capabilities, dict) and "supports_tool_calling" in selected_model_capabilities:
            supports_tools = bool(selected_model_capabilities.get("supports_tool_calling"))
        return ToolSelectionResult(
            recommended_tools=recommendations,
            not_selected=[],
            requires_tool_calling_model=bool(recommendations and supports_tools),
            candidate_count=len(candidates),
            stage="utility_model" if subagent.get("model") else "keyword",
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
    for item in output.get("recommended_tools", []) if isinstance(output, dict) and isinstance(output.get("recommended_tools"), list) else []:
        if isinstance(item, dict) and str(item.get("tool_id") or "") == tool_id:
            try:
                return float(item.get("confidence", 0.6))
            except (TypeError, ValueError):
                return 0.6
    return 0.6


def _reason(output: Any, tool_id: str) -> str:
    for item in output.get("recommended_tools", []) if isinstance(output, dict) and isinstance(output.get("recommended_tools"), list) else []:
        if isinstance(item, dict) and str(item.get("tool_id") or "") == tool_id:
            return str(item.get("reason") or "selected by tool selector")
    return "selected by keyword prefilter"
