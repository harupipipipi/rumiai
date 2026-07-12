from __future__ import annotations

from typing import Any


def import_task_board(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    return {"imported": False, "mode": "noop"}
