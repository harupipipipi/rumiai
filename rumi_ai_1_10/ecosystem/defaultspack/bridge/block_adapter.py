"""Compatibility bridge for legacy transport -> block dispatch.

Transport code should not import individual block handlers directly. This
module centralizes the legacy adapter path so block-backed transports can
continue to work while function-first routes become the primary path.
"""

from __future__ import annotations

import importlib
from typing import Any, Dict


def invoke_block(module_name: str, input_data: Dict[str, Any], context: Dict[str, Any]) -> Any:
    module = importlib.import_module(module_name)
    handler = getattr(module, "run", None)
    if handler is None:
        raise AttributeError(f"run not found in {module_name}")
    return handler(input_data, context)
