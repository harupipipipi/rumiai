from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class GatewayMessage:
    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    client_id: str = ""
    request_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
