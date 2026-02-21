"""Pip 依存ライブラリ ハンドラ Mixin"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from .._helpers import _log_internal_error, _SAFE_ERROR_MSG
from ...paths import is_path_within, ECOSYSTEM_DIR

# index_url 許可リスト — ここに含まれない URL は拒否する
_ALLOWED_INDEX_URLS: frozenset[str] = frozenset({
    "https://pypi.org/simple",
})

# Code root（ecosystem ディレクトリの親 = プロジェクトルート）
_CODE_ROOT: Path = Path(ECOSYSTEM_DIR).parent


class PipHandlersMixin:
    """pip 依存ライブラリ スキャン / 承認 / 拒否 / ブロック管理のハンドラ"""

    def _pip_scan(self, ecosystem_dir: Optional[str] = None) -> dict:
        if ecosystem_dir is not None:
            resolved = Path(ecosystem_dir).resolve()
            if not is_path_within(resolved, _CODE_ROOT):
                return {
                    "error": "ecosystem_dir is outside the allowed project root.",
                    "scanned_count": 0,
                    "pending_created": 0,
                }
        try:
            from ...pip_installer import get_pip_installer
            installer = get_pip_installer()
            result = installer.scan_candidates(ecosystem_dir)
            return result.to_dict()
        except Exception as e:
            _log_internal_error("pip_scan", e)
            return {"error": _SAFE_ERROR_MSG, "scanned_count": 0, "pending_created": 0}

    def _pip_list_requests(self, status_filter: str = "all") -> dict:
        try:
            from ...pip_installer import get_pip_installer
            installer = get_pip_installer()
            items = installer.list_items(status_filter)
            return {"items": items, "count": len(items), "status_filter": status_filter}
        except Exception as e:
            _log_internal_error("pip_list_requests", e)
            return {"items": [], "error": _SAFE_ERROR_MSG}

    def _pip_approve(self, candidate_key: str, allow_sdist: bool = False, index_url: str = "https://pypi.org/simple") -> dict:
        if index_url not in _ALLOWED_INDEX_URLS:
            return {
                "success": False,
                "error": f"index_url is not in the allowed list. Allowed: {sorted(_ALLOWED_INDEX_URLS)}",
            }
        try:
            from ...pip_installer import get_pip_installer
            installer = get_pip_installer()
            result = installer.approve_and_install(
                candidate_key, actor="api_user",
                allow_sdist=allow_sdist, index_url=index_url,
            )
            return result.to_dict()
        except Exception as e:
            _log_internal_error("pip_approve", e)
            return {"success": False, "error": _SAFE_ERROR_MSG}

    def _pip_reject(self, candidate_key: str, reason: str = "") -> dict:
        try:
            from ...pip_installer import get_pip_installer
            installer = get_pip_installer()
            result = installer.reject(candidate_key, actor="api_user", reason=reason)
            return result.to_dict()
        except Exception as e:
            _log_internal_error("pip_reject", e)
            return {"success": False, "error": _SAFE_ERROR_MSG}

    def _pip_list_blocked(self) -> dict:
        try:
            from ...pip_installer import get_pip_installer
            installer = get_pip_installer()
            blocked = installer.list_blocked()
            return {"blocked": blocked, "count": len(blocked)}
        except Exception as e:
            _log_internal_error("pip_list_blocked", e)
            return {"blocked": {}, "error": _SAFE_ERROR_MSG}

    def _pip_unblock(self, candidate_key: str, reason: str = "") -> dict:
        try:
            from ...pip_installer import get_pip_installer
            installer = get_pip_installer()
            result = installer.unblock(candidate_key, actor="api_user", reason=reason)
            return result.to_dict()
        except Exception as e:
            _log_internal_error("pip_unblock", e)
            return {"success": False, "error": _SAFE_ERROR_MSG}
