"""
app_lifecycle_manager.py - アプリケーションライフサイクル管理

セットアップ状態の確認・完了を一箇所に集約する薄いマネージャ。
core_setup の check_profile / save_profile を遅延 import で呼び出す。

Phase A で新規作成。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)


@dataclass
class AppLifecycleManager:
    """
    アプリケーションライフサイクル管理マネージャ。

    セットアップ状態の確認・完了を提供する。
    core_pack/core_setup の check_profile / save_profile を遅延 import し、
    Phase B の core_setup が存在しない環境でも ImportError にならない。
    """

    base_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parent.parent)

    def check_setup_status(self) -> Dict[str, Any]:
        """
        セットアップ状態を確認する。

        Returns:
            {"needs_setup": bool, "reason": str}
        """
        try:
            from .core_pack.core_setup.check_profile import check_profile
            return check_profile(base_dir=self.base_dir)
        except ImportError:
            logger.warning("core_setup.check_profile not available, assuming needs_setup=True")
            return {"needs_setup": True, "reason": "check_profile_unavailable"}
        except Exception as e:
            logger.error("check_setup_status failed: %s", e)
            return {"needs_setup": True, "reason": "check_error: {}".format(e)}

    def complete_setup(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        セットアップを完了する。

        save_profile() を呼び、成功後に check_profile() で検証する。

        Args:
            data: {"username": str, "language": str, "icon": optional, "occupation": optional}

        Returns:
            {"success": bool, "errors": list, ...}
        """
        try:
            from .core_pack.core_setup.save_profile import save_profile
        except ImportError:
            logger.error("core_setup.save_profile not available")
            return {"success": False, "errors": ["save_profile module not available"]}

        try:
            result = save_profile(data, base_dir=self.base_dir)
        except Exception as e:
            logger.error("complete_setup save_profile failed: %s", e)
            return {"success": False, "errors": ["save_profile failed: {}".format(e)]}

        if not result.get("success"):
            return result

        # 保存後に検証
        try:
            from .core_pack.core_setup.check_profile import check_profile
            verify = check_profile(base_dir=self.base_dir)
            if verify.get("needs_setup"):
                return {
                    "success": False,
                    "errors": ["Post-save verification failed: {}".format(verify.get("reason", "unknown"))],
                }
        except ImportError:
            pass  # 検証モジュールが無い場合は保存成功をそのまま返す
        except Exception as e:
            logger.warning("Post-save verification error: %s", e)

        return result

    def get_health(self) -> Dict[str, Any]:
        """
        ヘルスチェック情報を返す。

        Returns:
            {"status": "ok", "needs_setup": bool}
        """
        status = self.check_setup_status()
        return {
            "status": "ok",
            "needs_setup": status.get("needs_setup", True),
        }
