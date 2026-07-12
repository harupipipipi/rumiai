"""Execution policy helpers for pack function invocations."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Tuple

from .approval_manager import PackStatus, get_approval_manager
from .capability_grant_manager import get_capability_grant_manager
from .capability_trust_store import get_capability_trust_store
from .crypto_utils import compute_file_sha256


_HOST_GRANT_CALLING_CONVENTIONS = frozenset({"python_host", "binary", "command"})
_PROVIDER_ORIGINALS = {
    "get_approval_manager": get_approval_manager,
    "get_capability_grant_manager": get_capability_grant_manager,
    "get_capability_trust_store": get_capability_trust_store,
}


def _provider(name: str):
    """Resolve monkeypatched providers across core_runtime import aliases."""
    original = _PROVIDER_ORIGINALS[name]
    local_provider = globals().get(name, original)
    if local_provider is not original:
        return local_provider

    current_module = sys.modules.get(__name__)
    for module_name in (
        "core_runtime.pack_function_policy",
        "tobkiri_runtime.core_runtime.pack_function_policy",
    ):
        module = sys.modules.get(module_name)
        if module is None or module is current_module:
            continue
        candidate = getattr(module, name, None)
        other_originals = getattr(module, "_PROVIDER_ORIGINALS", {})
        if callable(candidate) and candidate is not other_originals.get(name):
            return candidate
    return local_provider


def _approval_manager():
    return _provider("get_approval_manager")()


def _grant_manager():
    return _provider("get_capability_grant_manager")()


def _trust_store():
    return _provider("get_capability_trust_store")()


def permission_id_for_entry(entry: Any) -> str:
    permission_id = getattr(entry, "permission_id", None)
    if isinstance(permission_id, str) and permission_id.strip():
        return permission_id.strip()
    qualified_name = getattr(entry, "qualified_name", None)
    if isinstance(qualified_name, str) and qualified_name.strip():
        return qualified_name.strip()
    return f"{entry.pack_id}:{entry.function_id}"


def _is_builtin_pack(entry: Any) -> bool:
    approval_manager = _approval_manager()
    pack_id = str(getattr(entry, "pack_id", "") or "").strip()
    return bool(
        getattr(approval_manager, "_is_core_pack", lambda _pack_id: False)(pack_id)
        or getattr(
            approval_manager,
            "_is_trusted_builtin_pack",
            lambda _pack_id: False,
        )(pack_id)
    )


def require_pack_approved(entry: Any) -> None:
    if _is_builtin_pack(entry):
        return

    status = _approval_manager().get_status(entry.pack_id)
    if status in (PackStatus.APPROVED, PackStatus.RUNNING):
        return

    if status is None:
        raise PermissionError(f"Pack is not approved: {entry.pack_id} (not_found)")
    raise PermissionError(f"Pack is not approved: {entry.pack_id} ({status.value})")


def require_pack_hash_current(entry: Any) -> None:
    if _is_builtin_pack(entry):
        return

    approval_manager = _approval_manager()
    if approval_manager.verify_hash(entry.pack_id, use_cache=False):
        return

    try:
        approval_manager.mark_modified(entry.pack_id)
    except Exception:
        pass
    raise PermissionError(f"Pack hash verification failed: {entry.pack_id}")


def require_function_trust_if_needed(entry: Any, entrypoint_path: Path | None) -> None:
    if _is_builtin_pack(entry) or entrypoint_path is None:
        return

    calling_convention = str(getattr(entry, "calling_convention", "") or "").strip()
    handler_py_sha256 = getattr(entry, "handler_py_sha256", None)
    trust_required = bool(
        handler_py_sha256
        or calling_convention in _HOST_GRANT_CALLING_CONVENTIONS
        or bool((getattr(entry, "manifest", {}) or {}).get("trust_required"))
    )
    if not trust_required:
        return

    trust_store = _trust_store()
    if not trust_store.is_loaded() and not trust_store.load():
        raise PermissionError("Capability trust store is unavailable")

    actual_sha256 = compute_file_sha256(entrypoint_path)
    trust_result = trust_store.is_trusted(permission_id_for_entry(entry), actual_sha256)
    if not trust_result.trusted:
        raise PermissionError(trust_result.reason)


def require_grant_if_needed(entry: Any) -> Dict[str, Any]:
    manifest_grant = getattr(entry, "grant_config", None)
    calling_convention = str(getattr(entry, "calling_convention", "") or "").strip()
    grant_required = manifest_grant is not None or calling_convention in _HOST_GRANT_CALLING_CONVENTIONS
    if not grant_required:
        return {}

    permission_id = permission_id_for_entry(entry)
    grant_result = _grant_manager().check(entry.pack_id, permission_id)
    if not grant_result.allowed:
        raise PermissionError(grant_result.reason)
    return dict(grant_result.config or {})


def validate_function_execution(entry: Any, entrypoint_path: Path | None) -> Tuple[str, Dict[str, Any]]:
    require_pack_approved(entry)
    require_pack_hash_current(entry)
    require_function_trust_if_needed(entry, entrypoint_path)
    grant_config = require_grant_if_needed(entry)
    calling_convention = str(getattr(entry, "calling_convention", "") or "").strip()
    return calling_convention, grant_config
