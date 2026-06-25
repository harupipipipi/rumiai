from __future__ import annotations

from typing import Any

from .service import compile_ui_plan


def ui_compile_plan(arguments: dict[str, Any] | None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    return compile_ui_plan(arguments, context)
