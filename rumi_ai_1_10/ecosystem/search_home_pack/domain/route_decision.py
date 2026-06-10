from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# Legacy route name kept for compatibility. The behavior is now:
# resolve the web intent and redirect to the best destination URL.
GOOGLE_REDIRECT = "GOOGLE_REDIRECT"
ASK_AI_WITH_SEARCH = "ASK_AI_WITH_SEARCH"


@dataclass(slots=True)
class RouteDecision:
    route_type: str = GOOGLE_REDIRECT
    query: str = ""
    target_url: str = ""
    target_candidates: list[dict[str, Any]] = field(default_factory=list)
    selected_index: int = -1
    fallback_url: str = ""
    resolution_reason: str = ""
    used_ai_judge: bool = False
    used_visual_judge: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def selected_candidate(self) -> dict[str, Any] | None:
        if self.selected_index < 0 or self.selected_index >= len(self.target_candidates):
            return None
        return self.target_candidates[self.selected_index]

    def to_dict(self) -> dict[str, Any]:
        return {
            "route_type": self.route_type,
            "query": self.query,
            "target_url": self.target_url,
            "target_candidates": [dict(item) for item in self.target_candidates],
            "selected_index": self.selected_index,
            "fallback_url": self.fallback_url,
            "resolution_reason": self.resolution_reason,
            "used_ai_judge": self.used_ai_judge,
            "used_visual_judge": self.used_visual_judge,
            "metadata": dict(self.metadata),
        }
