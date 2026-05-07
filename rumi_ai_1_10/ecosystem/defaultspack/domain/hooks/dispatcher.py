from __future__ import annotations

from typing import Any

from .registry import get_hook_registry


def dispatch_hook(point: str, payload: dict[str, Any] | None = None) -> list[str]:
    errors: list[str] = []
    for callback in get_hook_registry().callbacks(point):
        try:
            callback(payload or {})
        except Exception as exc:
            errors.append(str(exc))
    return errors
