from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


HookCallback = Callable[[dict[str, Any]], None]


@dataclass
class HookEvent:
    point: str
    payload: dict[str, Any] = field(default_factory=dict)
