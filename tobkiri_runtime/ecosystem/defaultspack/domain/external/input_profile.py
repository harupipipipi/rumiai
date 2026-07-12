from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class InputProfile:
    id: str
    provider: str
    version: int
    display_name: str
    spec: dict[str, Any]

    @classmethod
    def from_dict(cls, spec: dict[str, Any]) -> "InputProfile":
        return cls(
            id=str(spec.get("id") or ""),
            provider=str(spec.get("provider") or ""),
            version=int(spec.get("version") or 1),
            display_name=str(spec.get("display_name") or spec.get("id") or ""),
            spec=dict(spec),
        )
