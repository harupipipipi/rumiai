"""Import-safe virtual pointer state for non-physical cursor previews."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class VirtualPointerState:
    x: int = 0
    y: int = 0
    origin: str = "top_left"
    visible: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class VirtualPointer:
    """Small state holder for AI cursor movement that never moves the OS cursor."""

    def __init__(self, state: VirtualPointerState | dict[str, Any] | None = None) -> None:
        self._state = self._coerce_state(state)

    @property
    def state(self) -> VirtualPointerState:
        return self._state

    def position(self) -> dict[str, Any]:
        return self._state.to_dict()

    def move(self, x: Any, y: Any, **metadata: Any) -> dict[str, Any]:
        self._state = VirtualPointerState(
            x=self._coerce_int(x),
            y=self._coerce_int(y),
            origin=self._state.origin,
            visible=True,
            metadata={**self._state.metadata, **metadata},
        )
        return {
            "action": "move",
            "executed": True,
            "virtual_cursor": True,
            "target": {"x": self._state.x, "y": self._state.y},
            "pointer": self.position(),
        }

    def click(self, x: Any | None = None, y: Any | None = None, **metadata: Any) -> dict[str, Any]:
        if x is not None or y is not None:
            self.move(self._state.x if x is None else x, self._state.y if y is None else y, **metadata)
        return {
            "action": "click",
            "executed": True,
            "virtual_cursor": True,
            "target": {"x": self._state.x, "y": self._state.y},
            "pointer": self.position(),
        }

    def drag(self, x1: Any, y1: Any, x2: Any, y2: Any, **metadata: Any) -> dict[str, Any]:
        start = {"x": self._coerce_int(x1), "y": self._coerce_int(y1)}
        end = {"x": self._coerce_int(x2), "y": self._coerce_int(y2)}
        self.move(end["x"], end["y"], **metadata)
        return {
            "action": "drag",
            "executed": True,
            "virtual_cursor": True,
            "target": {"from": start, "to": end},
            "pointer": self.position(),
        }

    @classmethod
    def _coerce_state(cls, value: VirtualPointerState | dict[str, Any] | None) -> VirtualPointerState:
        if isinstance(value, VirtualPointerState):
            return value
        if isinstance(value, dict):
            return VirtualPointerState(
                x=cls._coerce_int(value.get("x", 0)),
                y=cls._coerce_int(value.get("y", 0)),
                origin=str(value.get("origin") or "top_left"),
                visible=bool(value.get("visible", True)),
                metadata=value.get("metadata") if isinstance(value.get("metadata"), dict) else {},
            )
        return VirtualPointerState()

    @staticmethod
    def _coerce_int(value: Any) -> int:
        try:
            return int(round(float(value)))
        except Exception:
            return 0
