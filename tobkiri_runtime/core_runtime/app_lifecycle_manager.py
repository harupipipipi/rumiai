"""
app_lifecycle_manager.py - アプリケーションライフサイクル管理

セットアップ状態の確認・完了を一箇所に集約する薄いマネージャ。
core_setup の check_profile / save_profile を遅延 import で呼び出す。

Phase A で新規作成。
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping

logger = logging.getLogger(__name__)


_RUNTIME_READINESS_LOCK = threading.Lock()
_RUNTIME_READINESS_STATE: Dict[str, Any] = {
    "panel_ready": False,
    "runtime_ready": False,
    "runtime_status": "starting",
    "runtime_error": None,
}


def reset_runtime_readiness() -> None:
    with _RUNTIME_READINESS_LOCK:
        _RUNTIME_READINESS_STATE.update(
            {
                "panel_ready": False,
                "runtime_ready": False,
                "runtime_status": "starting",
                "runtime_error": None,
            }
        )


def mark_panel_ready() -> None:
    with _RUNTIME_READINESS_LOCK:
        _RUNTIME_READINESS_STATE.update(
            {
                "panel_ready": True,
                "runtime_status": "panel_ready",
                "runtime_error": None,
            }
        )


def mark_runtime_ready() -> None:
    with _RUNTIME_READINESS_LOCK:
        _RUNTIME_READINESS_STATE.update(
            {
                "panel_ready": True,
                "runtime_ready": True,
                "runtime_status": "runtime_ready",
                "runtime_error": None,
            }
        )


def mark_runtime_failed(error: str) -> None:
    with _RUNTIME_READINESS_LOCK:
        _RUNTIME_READINESS_STATE.update(
            {
                "panel_ready": True,
                "runtime_ready": False,
                "runtime_status": "error",
                "runtime_error": error,
            }
        )


def get_runtime_readiness() -> Dict[str, Any]:
    with _RUNTIME_READINESS_LOCK:
        return dict(_RUNTIME_READINESS_STATE)


@dataclass
class AppLifecycleManager:
    """
    アプリケーションライフサイクル管理マネージャ。

    セットアップ状態の確認・完了を提供する。
    core_pack/core_setup の check_profile / save_profile を遅延 import し、
    Phase B の core_setup が存在しない環境でも ImportError にならない。
    """

    base_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parent.parent)
    _activation_lock: threading.Lock = field(
        default_factory=threading.Lock, init=False, repr=False
    )

    def check_setup_status(self) -> Dict[str, Any]:
        """
        セットアップ状態を確認する。

        Returns:
            {"needs_setup": bool, "reason": str}
        """
        from .bootstrap.profile_capture import (
            active_default_profile_exists,
            capture_default_profile,
        )

        if not active_default_profile_exists(base_dir=self.base_dir):
            result = {
                "needs_setup": True,
                "reason": "explicit_defaults_confirmation_required",
                "setup_state": "profile_transaction_required",
            }
            result.update(get_runtime_readiness())
            return result
        try:
            active = capture_default_profile(base_dir=self.base_dir)
            result = {
                "needs_setup": False,
                "reason": "canonical_v4_profile_captured",
                "setup_state": "complete",
                "profile_id": active.resolved.profile["profile_id"],
                "plan_digest": active.resolved.plan["plan_digest"],
                "activation_id": active.activation["activation_id"],
            }
        except Exception as error:
            logger.error("canonical v4 setup status failed: %s", error)
            result = {
                "needs_setup": True,
                "reason": "canonical_v4_profile_unavailable",
                "setup_state": "profile_transaction_required",
                "error_type": type(error).__name__,
            }

        result.update(get_runtime_readiness())
        return result

    def activate_default_profile(
        self, confirmation: Mapping[str, Any]
    ) -> Any:
        """Commit one confirmed activation and publish its Broker session."""

        from .authority.v4 import AuthorityStore
        from .bootstrap.production_v4 import capture_production_dispatch
        from .bootstrap.profile_capture import (
            capture_default_profile,
            runtime_user_data_root,
        )
        from .di_container import get_container
        from tobkiri_host.runtime import install_dispatch_session

        with self._activation_lock:
            active = capture_default_profile(
                base_dir=self.base_dir,
                confirmation=confirmation,
            )
            runtime_root = Path(__file__).resolve().parents[1]
            user_data = runtime_user_data_root(self.base_dir)
            session = capture_production_dispatch(
                active,
                bundle_root=runtime_root / "ecosystem" / "defaultspack" / "v4",
                ecosystem_root=runtime_root / "ecosystem",
                authority_store=AuthorityStore(
                    user_data / "authority" / "v4.sqlite3"
                ),
            )
            install_dispatch_session(get_container(), session)
            mark_runtime_ready()
            return active, session

    def complete_setup(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        セットアップを完了する。

        save_profile() を呼び、成功後に check_profile() で検証する。

        Args:
            data: {"username": str, "language": str, "icon": optional, "occupation": optional}

        Returns:
            {"success": bool, "errors": list, ...}
        """
        username = str(data.get("username") or "").strip()
        language = str(data.get("language") or "").strip()
        errors = []
        if not username:
            errors.append("username is required")
        if language not in {"en", "ja"}:
            errors.append("language must be en or ja")
        if errors:
            return {
                "success": False,
                "errors": errors,
                "setup_state": "invalid_request",
            }
        from .bootstrap.profile_capture import capture_default_profile
        try:
            active = capture_default_profile(base_dir=self.base_dir)
        except Exception as error:
            logger.error("canonical v4 setup transaction failed: %s", error)
            return {
                "success": False,
                "errors": ["canonical v4 Profile transaction failed"],
                "setup_state": "profile_transaction_failed",
                "error_type": type(error).__name__,
            }
        return {
            "success": True,
            "errors": [],
            "setup_state": "complete",
            "profile_id": active.resolved.profile["profile_id"],
            "plan_digest": active.resolved.plan["plan_digest"],
            "activation_id": active.activation["activation_id"],
            "restart_required": False,
        }

    def get_health(self) -> Dict[str, Any]:
        """
        ヘルスチェック情報を返す。

        Returns:
            {"status": "ok", "needs_setup": bool}
        """
        status = self.check_setup_status()
        return {
            "status": "error" if status.get("runtime_status") == "error" else "ok",
            "needs_setup": status.get("needs_setup", True),
            "panel_ready": status.get("panel_ready", False),
            "runtime_ready": status.get("runtime_ready", False),
            "runtime_status": status.get("runtime_status", "starting"),
            "runtime_error": status.get("runtime_error"),
        }
