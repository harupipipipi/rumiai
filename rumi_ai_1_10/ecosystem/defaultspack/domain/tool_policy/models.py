from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class ToolRisk(str, Enum):
    READ_ONLY = "read_only"
    FILE_WRITE = "file_write"
    FILE_DELETE = "file_delete"
    SHELL = "shell"
    NETWORK = "network"
    BROWSER = "browser"
    COMPUTER = "computer"
    CREDENTIAL = "credential"
    GIT_WRITE = "git_write"
    GIT_PUSH = "git_push"
    EXTERNAL_MESSAGE = "external_message"
    SCHEDULER_CREATE = "scheduler_create"
    CAPABILITY_MUTATION = "capability_mutation"
    PACK_INSTALL = "pack_install"


@dataclass
class PolicyDecision:
    allowed: bool
    risk: str
    action: str = "allow"
    requires_approval: bool = False
    reason: str = ""
    sandbox_mode: str = "read_only"
    matched_by: str | None = None
    matched_value: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
