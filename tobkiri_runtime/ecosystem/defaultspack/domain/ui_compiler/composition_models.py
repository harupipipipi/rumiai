from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import SCHEMA_VERSION


@dataclass(frozen=True)
class SelectionDecision:
    node_id: str
    accepted_candidate_id: str | None
    rejected: list[dict[str, Any]]
    decision: dict[str, Any]

    @property
    def passed(self) -> bool:
        return bool(self.accepted_candidate_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "nodeId": self.node_id,
            "acceptedCandidateId": self.accepted_candidate_id,
            "rejected": list(self.rejected),
            "decision": dict(self.decision),
        }


@dataclass(frozen=True)
class CompositionManifest:
    run_id: str
    source_root: str
    entry: str
    imports: list[dict[str, Any]]
    slot_mappings: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "runId": self.run_id,
            "sourceRoot": self.source_root,
            "entry": self.entry,
            "imports": list(self.imports),
            "slotMappings": list(self.slot_mappings),
        }


@dataclass(frozen=True)
class BuildVerificationReport:
    lint: str
    test: str
    build: str
    render_matrix: str
    compression: str
    console_errors: int = 0
    horizontal_overflow: int = 0
    commands: list[dict[str, Any]] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return (
            self.lint == "passed"
            and self.test == "passed"
            and self.build == "passed"
            and self.render_matrix == "passed"
            and self.compression == "passed"
            and self.console_errors == 0
            and self.horizontal_overflow == 0
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "lint": self.lint,
            "test": self.test,
            "build": self.build,
            "renderMatrix": self.render_matrix,
            "compression": self.compression,
            "consoleErrors": self.console_errors,
            "horizontalOverflow": self.horizontal_overflow,
            "commands": list(self.commands),
        }
