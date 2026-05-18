from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


COMPUTER_TOOL_IDS = {"computer_use", "browser_computer", "browser_use", "browser_companion"}


@dataclass
class ToolRecommendation:
    tool_id: str
    confidence: float = 0.0
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ToolSelectionResult:
    recommended_tools: list[ToolRecommendation] = field(default_factory=list)
    not_selected: list[dict[str, Any]] = field(default_factory=list)
    requires_tool_calling_model: bool = False
    candidate_count: int = 0
    stage: str = "keyword"

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommended_tools": [item.to_dict() for item in self.recommended_tools],
            "not_selected": list(self.not_selected),
            "requires_tool_calling_model": self.requires_tool_calling_model,
            "candidate_count": self.candidate_count,
            "stage": self.stage,
        }
