from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable


HookCallback = Callable[[dict[str, Any]], None]


class RuntimeHookRegistry:
    def __init__(self) -> None:
        self._callbacks: dict[str, list[HookCallback]] = defaultdict(list)

    def register(self, point: str, callback: HookCallback) -> None:
        self._callbacks[point].append(callback)

    def dispatch(self, point: str, payload: dict[str, Any] | None = None) -> None:
        for callback in list(self._callbacks.get(point, [])):
            callback(payload or {})


_registry = RuntimeHookRegistry()


def get_runtime_hooks() -> RuntimeHookRegistry:
    return _registry
