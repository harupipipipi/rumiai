"""
test_phase_a_health.py - /health エンドポイントのテスト

AppLifecycleManager の get_health() と
PackAPIHandler の /health エンドポイントをテストする。
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# core_setup のパスを追加
_CORE_SETUP_DIR = (
    Path(__file__).resolve().parent.parent
    / "core_runtime"
    / "core_pack"
    / "core_setup"
)
if str(_CORE_SETUP_DIR) not in sys.path:
    sys.path.insert(0, str(_CORE_SETUP_DIR))


class TestAppLifecycleManagerHealth:
    """AppLifecycleManager.get_health() のテスト"""

    def test_health_needs_setup_true(self, tmp_path):
        """profile.json が存在しない場合 -> needs_setup: True"""
        from core_runtime.app_lifecycle_manager import AppLifecycleManager
        alm = AppLifecycleManager(base_dir=tmp_path)
        result = alm.get_health()
        assert result["status"] == "ok"
        assert result["needs_setup"] is True

    def test_health_needs_setup_false(self, tmp_path):
        """profile.json が有効な場合 -> needs_setup: False"""
        from core_runtime.app_lifecycle_manager import AppLifecycleManager

        settings_dir = tmp_path / "user_data" / "settings"
        settings_dir.mkdir(parents=True)
        profile = {
            "schema_version": 1,
            "initialized_at": "2026-03-16T12:00:00Z",
            "username": "testuser",
            "language": "ja",
            "icon": None,
            "occupation": None,
            "setup_completed": True,
        }
        (settings_dir / "profile.json").write_text(
            json.dumps(profile), encoding="utf-8"
        )

        alm = AppLifecycleManager(base_dir=tmp_path)
        result = alm.get_health()
        assert result["status"] == "ok"
        assert result["needs_setup"] is False

    def test_health_returns_ok_status(self, tmp_path):
        """get_health() は常に status=ok を返す"""
        from core_runtime.app_lifecycle_manager import AppLifecycleManager
        alm = AppLifecycleManager(base_dir=tmp_path)
        result = alm.get_health()
        assert "status" in result
        assert "needs_setup" in result
        assert result["status"] == "ok"

    def test_health_no_auth_required(self):
        """/health は認証前に処理されること。"""
        from core_runtime.pack_api_server import PackAPIHandler

        handler = object.__new__(PackAPIHandler)
        handler.path = "/health"
        handler.client_address = ("198.51.100.7", 12345)
        handler._send_response = MagicMock()
        handler._check_auth = MagicMock(side_effect=AssertionError("auth should not run"))
        handler._match_web_mount = MagicMock(return_value=None)
        handler._check_rate_limit = MagicMock(return_value=True)
        PackAPIHandler.app_lifecycle_manager = MagicMock()
        PackAPIHandler.app_lifecycle_manager.get_health.return_value = {"status": "ok"}

        PackAPIHandler.do_GET(handler)

        handler._send_response.assert_called_once()
        handler._check_auth.assert_not_called()
