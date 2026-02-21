"""Capability Installer ハンドラ Mixin"""
from __future__ import annotations

from pathlib import Path
from typing import Optional
from urllib.parse import unquote

from .._helpers import _log_internal_error, _SAFE_ERROR_MSG
from ...paths import is_path_within, ECOSYSTEM_DIR

# Code root（ecosystem ディレクトリの親 = プロジェクトルート）
_CODE_ROOT: Path = Path(ECOSYSTEM_DIR).parent


class CapabilityInstallerHandlersMixin:
    """Capability Handler 候補スキャン / 承認 / 拒否 / ブロック管理のハンドラ"""

    @staticmethod
    def _extract_capability_key(path: str, prefix: str, suffix: str) -> Optional[str]:
        """
        URL パスから candidate_key を抽出し、URL デコードする。

        例: /api/capability/requests/my_pack%3Aslug%3Aid%3Asha/approve
        → "my_pack:slug:id:sha"
        """
        if not path.startswith(prefix) or not path.endswith(suffix):
            return None
        encoded_key = path[len(prefix):-len(suffix)]
        if not encoded_key:
            return None
        return unquote(encoded_key)

    def _capability_scan(self, ecosystem_dir: Optional[str] = None) -> dict:
        if ecosystem_dir is not None:
            resolved = Path(ecosystem_dir).resolve()
            if not is_path_within(resolved, _CODE_ROOT):
                return {
                    "error": "ecosystem_dir is outside the allowed project root.",
                    "scanned_count": 0,
                    "pending_created": 0,
                }
        try:
            from ...capability_installer import get_capability_installer
            installer = get_capability_installer()
            result = installer.scan_candidates(ecosystem_dir)
            return result.to_dict()
        except Exception as e:
            _log_internal_error("capability_scan", e)
            return {"error": _SAFE_ERROR_MSG, "scanned_count": 0, "pending_created": 0}

    def _capability_list_requests(self, status_filter: str = "all") -> dict:
        try:
            from ...capability_installer import get_capability_installer
            installer = get_capability_installer()
            items = installer.list_items(status_filter)
            return {"items": items, "count": len(items), "status_filter": status_filter}
        except Exception as e:
            _log_internal_error("capability_list_requests", e)
            return {"items": [], "error": _SAFE_ERROR_MSG}

    def _capability_approve(self, candidate_key: str, notes: str = "") -> dict:
        try:
            from ...capability_installer import get_capability_installer
            installer = get_capability_installer()
            result = installer.approve_and_install(candidate_key, actor="api_user", notes=notes)
            return result.to_dict()
        except Exception as e:
            _log_internal_error("capability_approve", e)
            return {"success": False, "error": _SAFE_ERROR_MSG}

    def _capability_reject(self, candidate_key: str, reason: str = "") -> dict:
        try:
            from ...capability_installer import get_capability_installer
            installer = get_capability_installer()
            result = installer.reject(candidate_key, actor="api_user", reason=reason)
            return result.to_dict()
        except Exception as e:
            _log_internal_error("capability_reject", e)
            return {"success": False, "error": _SAFE_ERROR_MSG}

    def _capability_list_blocked(self) -> dict:
        try:
            from ...capability_installer import get_capability_installer
            installer = get_capability_installer()
            blocked = installer.list_blocked()
            return {"blocked": blocked, "count": len(blocked)}
        except Exception as e:
            _log_internal_error("capability_list_blocked", e)
            return {"blocked": {}, "error": _SAFE_ERROR_MSG}

    def _capability_unblock(self, candidate_key: str, reason: str = "") -> dict:
        try:
            from ...capability_installer import get_capability_installer
            installer = get_capability_installer()
            result = installer.unblock(candidate_key, actor="api_user", reason=reason)
            return result.to_dict()
        except Exception as e:
            _log_internal_error("capability_unblock", e)
            return {"success": False, "error": _SAFE_ERROR_MSG}
