from __future__ import annotations

from collections import defaultdict

from .models import HookCallback


class HookRegistry:
    def __init__(self) -> None:
        self._callbacks: dict[str, list[HookCallback]] = defaultdict(list)

    def register(self, point: str, callback: HookCallback) -> None:
        self._callbacks[point].append(callback)

    def callbacks(self, point: str) -> list[HookCallback]:
        return list(self._callbacks.get(point, []))

    def clear(self) -> None:
        self._callbacks.clear()


_registry = HookRegistry()


def get_hook_registry() -> HookRegistry:
    return _registry
