from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import SCHEMA_VERSION


@dataclass(frozen=True)
class FoundationSpec:
    candidate_id: str
    direction: dict[str, Any]
    typography: dict[str, Any]
    spacing: dict[str, Any]
    color: dict[str, Any]
    surface: dict[str, Any]
    primitives: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "candidateId": self.candidate_id,
            "direction": dict(self.direction),
            "typography": dict(self.typography),
            "spacing": dict(self.spacing),
            "color": dict(self.color),
            "surface": dict(self.surface),
            "primitives": list(self.primitives),
        }


@dataclass(frozen=True)
class FoundationCandidate:
    candidate_id: str
    root: str
    spec: FoundationSpec
    score: float
    report: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "candidateId": self.candidate_id,
            "root": self.root,
            "foundation": self.spec.to_dict(),
            "score": self.score,
            "report": dict(self.report),
        }
