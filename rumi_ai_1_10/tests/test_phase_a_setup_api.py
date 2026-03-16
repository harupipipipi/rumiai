"""
test_phase_a_setup_api.py - /api/setup/status, /api/setup/complete のテスト

AppLifecycleManager の check_setup_status() / complete_setup() と
PackAPIHandler のセットアップ API エンドポイントをテストする。
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
        """/api/setup/status は認証不要であること"""
        import inspect
        from core_runtime.pack_api_server import PackAPIHandler

        source = inspect.getsource(PackAPIHandler.do_GET)
        setup_pos = source.find('"/api/setup/status"')
        auth_pos = source.find('_check_auth()')
        assert setup_pos != -1, "/api/setup/status not found in do_GET"
        assert setup_pos < auth_pos, "/api/setup/status must appear before _check_auth"

    def test_setup_complete_no_auth_required(self):
        """/api/setup/complete は認証不要であること"""
        import inspect
        from core_runtime.pack_api_server import PackAPIHandler

        source = inspect.getsource(PackAPIHandler.do_POST)
        complete_pos = source.find('"/api/setup/complete"')
        auth_pos = source.find('_check_auth()')
        assert complete_pos != -1, "/api/setup/complete not found in do_POST"
        assert complete_pos < auth_pos, "/api/setup/complete must appear before _check_auth"
