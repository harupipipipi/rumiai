from __future__ import annotations

from dataclasses import dataclass, field
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
