"""
test_phase_a_setup_api.py - /api/setup/status, /api/setup/complete のテスト

AppLifecycleManager の check_setup_status() / complete_setup() と
PackAPIHandler のセットアップ API エンドポイントをテストする。
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

# core_setup のパスを追加
_CORE_SETUP_DIR = (
    Path(__file__).resolve().parent.parent
    / "core_runtime"
    / "core_pack"
    / "core_setup"
)
if str(_CORE_SETUP_DIR) not in sys.path:
    sys.path.insert(0, str(_CORE_SETUP_DIR))


class TestCheckSetupStatus:
    """AppLifecycleManager.check_setup_status() のテスト"""

    def test_needs_setup_when_no_profile(self, tmp_path):
        """profile.json が無い -> needs_setup: True"""
        from core_runtime.app_lifecycle_manager import AppLifecycleManager
        alm = AppLifecycleManager(base_dir=tmp_path)
        result = alm.check_setup_status()
        assert result["needs_setup"] is True
        assert "reason" in result

    def test_not_needs_setup_when_profile_valid(self, tmp_path):
        """profile.json が有効 -> needs_setup: False"""
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
        result = alm.check_setup_status()
        assert result["needs_setup"] is False

    def test_setup_status_includes_runtime_readiness(self, tmp_path):
        from core_runtime.app_lifecycle_manager import (
            AppLifecycleManager,
            mark_panel_ready,
            reset_runtime_readiness,
        )

        reset_runtime_readiness()
        mark_panel_ready()

        alm = AppLifecycleManager(base_dir=tmp_path)
        result = alm.check_setup_status()

        assert result["panel_ready"] is True
        assert result["runtime_ready"] is False
        assert result["runtime_status"] == "panel_ready"


class TestCompleteSetup:
    """AppLifecycleManager.complete_setup() のテスト"""

    def test_complete_setup_valid(self, tmp_path):
        """有効なデータでセットアップ完了"""
        from core_runtime.app_lifecycle_manager import AppLifecycleManager
        alm = AppLifecycleManager(base_dir=tmp_path)
        result = alm.complete_setup({
            "username": "testuser",
            "language": "ja",
        })
        assert result["success"] is True
        assert result["errors"] == []

        # profile.json が作成されたことを確認
        profile_path = tmp_path / "user_data" / "settings" / "profile.json"
        assert profile_path.exists()

        # check_setup_status で検証
        status = alm.check_setup_status()
        assert status["needs_setup"] is False

    def test_complete_setup_no_username(self, tmp_path):
        """username が空 -> エラー"""
        from core_runtime.app_lifecycle_manager import AppLifecycleManager
        alm = AppLifecycleManager(base_dir=tmp_path)
        result = alm.complete_setup({
            "username": "",
            "language": "ja",
        })
        assert result["success"] is False
        assert len(result["errors"]) > 0

    def test_complete_setup_bad_language(self, tmp_path):
        """language が不正 -> エラー"""
        from core_runtime.app_lifecycle_manager import AppLifecycleManager
        alm = AppLifecycleManager(base_dir=tmp_path)
        result = alm.complete_setup({
            "username": "testuser",
            "language": "xx",
        })
        assert result["success"] is False
        assert len(result["errors"]) > 0

    def test_complete_setup_missing_username(self, tmp_path):
        """username が無い -> エラー"""
        from core_runtime.app_lifecycle_manager import AppLifecycleManager
        alm = AppLifecycleManager(base_dir=tmp_path)
        result = alm.complete_setup({
            "language": "ja",
        })
        assert result["success"] is False

    def test_complete_setup_with_optional_fields(self, tmp_path):
        """オプションフィールド付きでセットアップ完了"""
        from core_runtime.app_lifecycle_manager import AppLifecycleManager
        alm = AppLifecycleManager(base_dir=tmp_path)
        result = alm.complete_setup({
            "username": "testuser",
            "language": "en",
            "icon": "/path/to/icon.png",
            "occupation": "Developer",
        })
        assert result["success"] is True

    def test_setup_status_no_auth_required(self):
        """/api/setup/status は認証前に処理されること。"""
        from core_runtime.pack_api_server import PackAPIHandler

        handler = object.__new__(PackAPIHandler)
        handler.path = "/api/setup/status"
        handler.client_address = ("198.51.100.7", 12345)
        handler._send_response = MagicMock()
        handler._check_auth = MagicMock(side_effect=AssertionError("auth should not run"))
        handler._match_web_mount = MagicMock(return_value=None)
        handler._check_rate_limit = MagicMock(return_value=True)
        handler._is_pre_auth_route = MagicMock(return_value=True)
        PackAPIHandler.app_lifecycle_manager = MagicMock()
        PackAPIHandler.app_lifecycle_manager.check_setup_status.return_value = {
            "needs_setup": True,
        }

        PackAPIHandler.do_GET(handler)

        handler._send_response.assert_called_once()
        handler._check_auth.assert_not_called()

    def test_setup_complete_no_auth_required(self):
        """/api/setup/complete は認証前に処理されること。"""
        from core_runtime.pack_api_server import PackAPIHandler

        handler = object.__new__(PackAPIHandler)
        handler.path = "/api/setup/complete"
        handler.client_address = ("198.51.100.7", 12345)
        handler._send_response = MagicMock()
        handler._check_auth = MagicMock(side_effect=AssertionError("auth should not run"))
        handler._check_rate_limit = MagicMock(return_value=True)
        handler._is_pre_auth_route = MagicMock(return_value=True)
        handler._parse_body = MagicMock(return_value={"username": "testuser", "language": "ja"})
        PackAPIHandler.app_lifecycle_manager = MagicMock()
        PackAPIHandler.app_lifecycle_manager.complete_setup.return_value = {
            "success": True,
            "errors": [],
        }
        PackAPIHandler.kernel = None

        PackAPIHandler.do_POST(handler)

        handler._send_response.assert_called_once()
        handler._check_auth.assert_not_called()

    def test_setup_packs_list_no_auth_required_during_initial_setup(self):
        from core_runtime.pack_api_server import PackAPIHandler

        handler = object.__new__(PackAPIHandler)
        handler.path = "/api/setup/packs"
        handler.client_address = ("198.51.100.7", 12345)
        handler._check_rate_limit = MagicMock(return_value=True)
        handler._handle_builtin_public_get = MagicMock(return_value=False)
        handler._match_web_mount = MagicMock(return_value=None)
        handler._check_auth = MagicMock(side_effect=AssertionError("auth should not run"))
        handler._parse_query = MagicMock(return_value={})
        handler._dispatch_api_route = MagicMock(return_value=True)
        handler._send_response = MagicMock()
        PackAPIHandler.app_lifecycle_manager = MagicMock()
        PackAPIHandler.app_lifecycle_manager.check_setup_status.return_value = {
            "needs_setup": True,
        }

        PackAPIHandler.do_GET(handler)

        handler._check_auth.assert_not_called()
        handler._dispatch_api_route.assert_called_once_with("GET", "/api/setup/packs", query={})

    def test_setup_pack_install_no_auth_required_only_during_initial_setup(self):
        from core_runtime.pack_api_server import PackAPIHandler

        handler = object.__new__(PackAPIHandler)
        handler.path = "/api/setup/packs/install"
        handler.client_address = ("198.51.100.7", 12345)
        handler._check_rate_limit = MagicMock(return_value=True)
        handler._check_auth = MagicMock(side_effect=AssertionError("auth should not run"))
        handler._parse_body = MagicMock(return_value={"setup_pack_ids": ["defaultspack"]})
        handler._parse_query = MagicMock(return_value={})
        handler._dispatch_api_route = MagicMock(return_value=True)
        handler._send_response = MagicMock()
        PackAPIHandler.app_lifecycle_manager = MagicMock()
        PackAPIHandler.app_lifecycle_manager.check_setup_status.return_value = {
            "needs_setup": True,
        }

        PackAPIHandler.do_POST(handler)

        handler._check_auth.assert_not_called()
        handler._dispatch_api_route.assert_called_once_with(
            "POST",
            "/api/setup/packs/install",
            {"setup_pack_ids": ["defaultspack"]},
            query={},
        )

    def test_setup_pack_install_requires_auth_after_setup_completed(self):
        from core_runtime.pack_api_server import PackAPIHandler

        handler = object.__new__(PackAPIHandler)
        handler.path = "/api/setup/packs/install"
        handler.client_address = ("198.51.100.7", 12345)
        handler._check_rate_limit = MagicMock(return_value=True)
        handler._check_auth = MagicMock(return_value=False)
        handler._discard_request_body = MagicMock()
        handler._dispatch_api_route = MagicMock(return_value=True)
        handler._send_response = MagicMock()
        PackAPIHandler.app_lifecycle_manager = MagicMock()
        PackAPIHandler.app_lifecycle_manager.check_setup_status.return_value = {
            "needs_setup": False,
        }

        PackAPIHandler.do_POST(handler)

        handler._check_auth.assert_called_once_with("POST", "/api/setup/packs/install")
        handler._discard_request_body.assert_called_once()
        handler._dispatch_api_route.assert_not_called()


class TestHealthPayload:
    def test_health_reports_runtime_error(self, tmp_path):
        from core_runtime.app_lifecycle_manager import (
            AppLifecycleManager,
            mark_runtime_failed,
            reset_runtime_readiness,
        )

        reset_runtime_readiness()
        mark_runtime_failed("runtime crashed")

        alm = AppLifecycleManager(base_dir=tmp_path)
        result = alm.get_health()

        assert result["status"] == "error"
        assert result["runtime_status"] == "error"
        assert result["runtime_error"] == "runtime crashed"
        reset_runtime_readiness()
