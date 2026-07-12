from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import SCHEMA_VERSION


@dataclass(frozen=True)
class CompressionIssue:
    code: str
    severity: str
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class CompressionReport:
    node_id: str
    candidate_id: str
    status: str
    compression_score: float
    metrics: dict[str, float]
    issues: list[CompressionIssue] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.status == "pass"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "nodeId": self.node_id,
            "candidateId": self.candidate_id,
            "status": self.status,
            "compressionScore": self.compression_score,
            "metrics": dict(self.metrics),
            "issues": [issue.to_dict() for issue in self.issues],
        }
