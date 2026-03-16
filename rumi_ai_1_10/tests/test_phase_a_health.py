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
        """/health は認証ヘッダーなしでもアクセス可能であること（設計確認）。

        PackAPIHandler の do_GET で _check_auth() の前に分岐されることを
        コードレベルで検証する。
        """
        import inspect
        from core_runtime.pack_api_server import PackAPIHandler

        source = inspect.getsource(PackAPIHandler.do_GET)
        # /health の分岐が _check_auth の前にあることを確認
        health_pos = source.find('"/health"')
        auth_pos = source.find('_check_auth()')
        assert health_pos != -1, "/health endpoint not found in do_GET"
        assert auth_pos != -1, "_check_auth not found in do_GET"
        assert health_pos < auth_pos, "/health must appear before _check_auth in do_GET"
