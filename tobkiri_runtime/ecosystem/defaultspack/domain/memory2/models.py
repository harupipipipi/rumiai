from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class MemoryEntry:
    id: str
    scope: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    agent_id: str | None = None
    project_id: str | None = None
    source: str = "manual"
    confidence: float = 1.0
    created_at: str = ""
    updated_at: str = ""
    archived_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
