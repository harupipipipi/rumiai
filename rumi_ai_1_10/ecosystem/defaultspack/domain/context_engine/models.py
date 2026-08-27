from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class PromptLayer:
    name: str
    content: Any
    stable: bool = True
    token_estimate: int = 0


@dataclass
class ContextBuildResult:
    messages: list[dict[str, Any]]
    system_prompt_hash: str
    token_estimate: int
    attached_tools: list[Any] = field(default_factory=list)
    pinned_context: list[Any] = field(default_factory=list)
    ephemeral_context: list[Any] = field(default_factory=list)


@dataclass(frozen=True)
class ContextSectionBudget:
    name: str
    max_items: int = 0
    max_tokens: int = 0


@dataclass
class ContextValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    sections: dict[str, dict[str, int]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
