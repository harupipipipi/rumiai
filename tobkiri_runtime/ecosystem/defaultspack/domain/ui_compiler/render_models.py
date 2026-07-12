from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import SCHEMA_VERSION


@dataclass(frozen=True)
class RenderSnapshot:
    subject_id: str
    candidate_id: str
    viewport: int
    scenario: str
    text_scale: float
    image_path: str
    dom_path: str
    console_path: str
    metrics: dict[str, Any] = field(default_factory=dict)

    def key(self) -> str:
        scale = str(self.text_scale).replace(".", "-")
        return f"{self.viewport}-{self.scenario}-text-{scale}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "subjectId": self.subject_id,
            "candidateId": self.candidate_id,
            "viewport": self.viewport,
            "scenario": self.scenario,
            "textScale": self.text_scale,
            "imagePath": self.image_path,
            "domPath": self.dom_path,
            "consolePath": self.console_path,
            "metrics": dict(self.metrics),
        }


@dataclass(frozen=True)
class RenderMatrix:
    subject_id: str
    candidate_id: str
    snapshots: list[RenderSnapshot]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "subjectId": self.subject_id,
            "candidateId": self.candidate_id,
            "snapshots": [snapshot.to_dict() for snapshot in self.snapshots],
        }
