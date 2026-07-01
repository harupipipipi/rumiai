from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

PACK_ROOT = Path(__file__).resolve().parents[2]
RUMI_ROOT = PACK_ROOT.parents[1]
for root_path in (str(PACK_ROOT), str(RUMI_ROOT)):
    if root_path not in sys.path:
        sys.path.insert(0, root_path)


def run(context: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    from domain.function_runtime.dispatcher import run_defaultspack_function
    from domain.function_runtime.response import error

    handler_id = str((context or {}).get("handler_id") or "")
    function_id = handler_id.split(":", 1)[-1].strip()
    if not function_id:
        return error("template-backed function id is missing", "INVALID_TEMPLATE_FUNCTION")
    return run_defaultspack_function(function_id, args or {}, context or {})
