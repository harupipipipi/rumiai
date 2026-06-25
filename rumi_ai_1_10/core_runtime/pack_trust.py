from __future__ import annotations

from typing import Any


def is_pack_trusted(pack_id: str, approval_manager: Any = None) -> tuple[bool, str | None]:
    """Return whether a pack is approved and hash-verified.

    This is intentionally tiny and passive so content loaders can share the
    same trust boundary without importing pack execution code.
    """
    normalized = str(pack_id or "").strip()
    if not normalized:
        return False, "missing_pack_id"
    manager = approval_manager
    if manager is None:
        try:
            from .approval_manager import get_approval_manager

            manager = get_approval_manager()
        except Exception as exc:
            return False, f"approval_manager_unavailable:{exc}"
    checker = getattr(manager, "is_pack_approved_and_verified", None)
    if not callable(checker):
        return False, "approval_checker_unavailable"
    try:
        result = checker(normalized)
    except Exception as exc:
        return False, f"approval_check_error:{exc}"
    if isinstance(result, tuple):
        ok = bool(result[0])
        reason = result[1] if len(result) > 1 else None
        return ok, str(reason) if reason is not None else None
    return bool(result), None
