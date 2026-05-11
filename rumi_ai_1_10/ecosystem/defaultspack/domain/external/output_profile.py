from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class OutputProfile:
    id: str
    provider: str
    version: int
    display_name: str
    transport: str
    spec: dict[str, Any]

    @classmethod
    def from_dict(cls, spec: dict[str, Any]) -> "OutputProfile":
        return cls(
            id=str(spec.get("id") or ""),
            provider=str(spec.get("provider") or ""),
            version=int(spec.get("version") or 1),
            display_name=str(spec.get("display_name") or spec.get("id") or ""),
            transport=str(spec.get("transport") or spec.get("provider") or "generic"),
            spec=dict(spec),
        )
