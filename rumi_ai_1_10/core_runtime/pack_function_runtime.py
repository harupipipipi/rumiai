"""Generic pack function invocation helper."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Dict, Optional

from .paths import (
    BASE_DIR,
    CORE_PACK_DIR,
    CORE_PACK_ID_PREFIX,
    ECOSYSTEM_DIR,
    is_path_within,
)
from .validation import validate_entrypoint


def _is_pack_approved_and_verified(pack_id: str) -> tuple[bool, Optional[str]]:
    try:
        from .approval_manager import get_approval_manager

        result = get_approval_manager().is_pack_approved_and_verified(pack_id)
    except Exception as exc:
        return False, f"approval_check_error:{exc}"
    if isinstance(result, tuple):
        return bool(result[0]), result[1] if len(result) > 1 else None
    return bool(result), None


TRUSTED_IN_PROCESS_PACK_IDS = frozenset({"defaultspack", "rumi_default_tools_pack"})


def _find_pack_root(path_hint: Any) -> Optional[Path]:
    try:
        candidate = Path(path_hint).resolve()
    except (OSError, TypeError):
        return None
    if candidate.is_file():
        candidate = candidate.parent
    for current in (candidate, *candidate.parents):
        if (current / "ecosystem.json").is_file():
            return current
    return candidate


def _is_pack_root_under(pack_root: Path, allowed_root: Path, pack_id: str) -> bool:
    try:
        resolved_pack = pack_root.resolve()
    except OSError:
        resolved_pack = pack_root
    try:
        resolved_allowed = allowed_root.resolve()
    except OSError:
        resolved_allowed = allowed_root
    try:
        relative = resolved_pack.relative_to(resolved_allowed)
    except ValueError:
        return False
    return bool(relative.parts) and relative.parts[0] == pack_id


def is_pack_function_in_process_allowed(
    pack_id: str,
    pack_root_hint: Any = None,
) -> bool:
    """Return True only for first-party pack functions allowed in this process."""
    normalized_pack_id = str(pack_id or "").strip()
    if not normalized_pack_id:
        return False

    pack_root = _find_pack_root(pack_root_hint) if pack_root_hint is not None else None

    if normalized_pack_id.startswith(CORE_PACK_ID_PREFIX):
        if pack_root is None:
            pack_root = Path(CORE_PACK_DIR) / normalized_pack_id
            if not pack_root.is_dir():
                return False
        return _is_pack_root_under(
            pack_root,
            Path(CORE_PACK_DIR),
            normalized_pack_id,
        )

    if normalized_pack_id not in TRUSTED_IN_PROCESS_PACK_IDS:
        return False

    if pack_root is None:
        pack_root = Path(ECOSYSTEM_DIR) / normalized_pack_id
        if not pack_root.is_dir():
            return False
    if _is_pack_root_under(pack_root, Path(ECOSYSTEM_DIR), normalized_pack_id):
        return True

    try:
        resolved = pack_root.resolve()
    except OSError:
        resolved = pack_root
    if resolved.name != normalized_pack_id or resolved.parent.name != "ecosystem":
        return False
    return resolved.parent.parent.name == "app"


def invoke_pack_function(
    pack_id: str,
    function_id: str,
    args: Optional[Dict[str, Any]] = None,
    context: Optional[Dict[str, Any]] = None,
) -> Any:
    from .di_container import get_container

    qualified_name = (
        function_id if ":" in function_id else f"{pack_id}:{function_id}"
    )
    entry = get_container().get("function_registry").get(qualified_name)
    if entry is None:
        raise KeyError(f"Function not found: {qualified_name}")
    if not is_pack_function_in_process_allowed(entry.pack_id, entry.function_dir):
        raise PermissionError(
            f"In-process pack function execution is not allowed: {qualified_name}"
        )
    approved, reason = _is_pack_approved_and_verified(entry.pack_id)
    if not approved:
        detail = f": {reason}" if reason else ""
        raise PermissionError(f"Pack not approved: {entry.pack_id}{detail}")

    entrypoint = entry.entrypoint or "main.py:run"
    function_dir = Path(entry.function_dir)
    valid, error, module_path = validate_entrypoint(entrypoint, function_dir)
    if not valid or module_path is None:
        raise PermissionError(error or f"Invalid entrypoint: {entrypoint}")
    _, callable_name = entrypoint.rsplit(":", 1)
    if not module_path.is_file():
        raise FileNotFoundError(f"Entrypoint file not found: {module_path}")
    if not is_path_within(module_path, BASE_DIR):
        raise PermissionError(f"Entrypoint escapes project boundary: {module_path}")
    trusted_path = getattr(entry, "main_py_path", None)
    if trusted_path is not None and Path(trusted_path).resolve() != module_path.resolve():
        raise PermissionError(
            f"Entrypoint differs from trusted registry path: {module_path}"
        )

    spec = importlib.util.spec_from_file_location(
        f"pack_function_{qualified_name.replace(':', '_')}",
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
