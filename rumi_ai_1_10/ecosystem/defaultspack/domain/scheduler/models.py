from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class SchedulerJob:
    job_id: str
    name: str
    kind: str
    schedule: str
    prompt: str = ""
    agent_id: str = "main"
    session_target: str = "fresh"
    context_from: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    enabled_toolsets: list[str] = field(default_factory=list)
    runtime_profile_key: str = ""
    deliver: str = "local"
    no_agent: bool = False
    script: str | None = None
    enabled: bool = True
    next_run_at: str = ""
    last_run_at: str = ""
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
