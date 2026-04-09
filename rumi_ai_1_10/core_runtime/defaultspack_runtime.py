"""
defaultspack_runtime.py - lightweight function-first runtime helper

These helpers intentionally resolve defaultspack functions via FunctionRegistry
so the new pack can use the same discoverable function surface as the rest of
the runtime, while keeping the HTTP handlers in core space.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Dict, Optional


def invoke_defaultspack_function(
    qualified_name: str,
    args: Optional[Dict[str, Any]] = None,
    context: Optional[Dict[str, Any]] = None,
) -> Any:
    from .di_container import get_container

    entry = get_container().get("function_registry").get(qualified_name)
    if entry is None:
        raise KeyError(f"Function not found: {qualified_name}")

    entrypoint = entry.entrypoint or "main.py:run"
    module_rel, callable_name = (
        entrypoint.rsplit(":", 1) if ":" in entrypoint else (entrypoint, "run")
    )
    module_path = Path(entry.function_dir) / module_rel
    if not module_path.is_file():
        raise FileNotFoundError(f"Entrypoint file not found: {module_path}")

    spec = importlib.util.spec_from_file_location(
        f"defaultspack_runtime_{qualified_name.replace(':', '_')}",
        str(module_path),
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load module: {module_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fn = getattr(module, callable_name, None)
    if fn is None:
        raise AttributeError(f"Callable '{callable_name}' not found in {module_path}")

    call_context = dict(context or {})
    call_context.setdefault("pack_id", entry.pack_id)
    call_context.setdefault("qualified_name", qualified_name)
    return fn(call_context, dict(args or {}))
