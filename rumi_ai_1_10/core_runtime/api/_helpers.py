"""
共通ヘルパー — 全ハンドラ Mixin から使用。
pack_api_server.py との循環 import を回避するため独立モジュールとした。
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_SAFE_ERROR_MSG = "Internal server error"


def _log_internal_error(context: str, exc: Exception) -> None:
    """Log exception details to audit log (or fallback to logger) without exposing to client."""
    try:
        from ..audit_logger import get_audit_logger
        audit = get_audit_logger()
        audit.log_system_event(
            event_type="api_internal_error",
            success=False,
            details={"context": context, "error": str(exc), "type": type(exc).__name__},
        )
    except Exception:
        logger.exception(f"Internal error in {context}: {exc}")
