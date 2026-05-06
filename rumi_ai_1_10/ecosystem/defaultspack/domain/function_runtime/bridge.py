from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from .context import principal_from_context
from .response import error, normalize_output


def ensure_defaultspack_functions_registered(container: Any | None = None) -> int:
    """Register generated defaultspack functions into the shared DI registry."""
    if container is None:
        try:
            from core_runtime.di_container import get_container

            container = get_container()
        except Exception:
            return 0
    try:
        registry = container.get_or_none("function_registry")
    except Exception:
        registry = None
    if registry is None:
        return 0

    functions_root = Path(__file__).resolve().parents[2] / "functions"
    if not functions_root.is_dir():
        return 0
    registered = 0
    for function_dir in sorted(path for path in functions_root.iterdir() if path.is_dir()):
        manifest_path = function_dir / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        function_id = str(manifest.get("function_id") or function_dir.name).strip()
        if not function_id:
            continue
        try:
            if registry.register(
                pack_id="defaultspack",
                function_id=function_id,
                manifest=manifest,
                function_dir=function_dir,
            ):
                registered += 1
        except Exception:
            continue
    return registered


def invoke_function(
    qualified_name: str,
    args: dict[str, Any] | None,
    context: dict[str, Any] | None = None,
    principal_id: str = "defaultspack",
) -> dict[str, Any]:
    """Invoke a Rumi function through the shared CapabilityExecutor."""
    try:
        from core_runtime.di_container import get_container
    except Exception as exc:
        return error(f"Capability runtime is unavailable: {exc}", "CAPABILITY_RUNTIME_UNAVAILABLE")

    principal = principal_id or principal_from_context(context)
    request = {
        "type": "function.call",
        "qualified_name": qualified_name,
        "args": dict(args or {}),
        "request_id": str((context or {}).get("request_id") or uuid.uuid4()),
    }
    try:
        container = get_container()
        if qualified_name.startswith("defaultspack:") or qualified_name.startswith("defaults."):
            ensure_defaultspack_functions_registered(container)
        executor = container.get_or_none("capability_executor")
        if executor is None:
            from core_runtime.capability_executor import get_capability_executor

            executor = get_capability_executor()
        response = executor.execute(principal, request)
    except Exception as exc:
        return error(f"Capability execution failed: {exc}", "CAPABILITY_EXECUTION_FAILED")

    if not getattr(response, "success", False):
        return error(
            getattr(response, "error", None) or "Function call failed",
            (getattr(response, "error_type", None) or "FUNCTION_CALL_FAILED").upper(),
        )
    return normalize_output(getattr(response, "output", None))


def invoke_defaultspack_function(
    function_id: str,
    args: dict[str, Any] | None,
    context: dict[str, Any] | None = None,
    principal_id: str = "defaultspack",
) -> dict[str, Any]:
    qualified_name = function_id if ":" in function_id else f"defaultspack:{function_id}"
    return invoke_function(qualified_name, args, context, principal_id)
