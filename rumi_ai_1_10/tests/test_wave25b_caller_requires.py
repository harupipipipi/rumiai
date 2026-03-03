"""
W25-B: check_caller_requires() のテスト
"""
import os
import sys
import pytest

# rumi_ai_1_10 をパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# DI container / approval_manager の import を回避するため環境変数でモードを固定
# PermissionManager を直接インスタンス化する


class TestCheckCallerRequiresPermissive:
    """permissive モードのテスト"""

    def _make_pm(self):
        from core_runtime.permission_manager import PermissionManager
        return PermissionManager(mode="permissive")

    def test_empty_list_returns_true(self):
        """空リストの場合 True"""
        pm = self._make_pm()
        assert pm.check_caller_requires("caller_1", []) is True

    def test_none_returns_true(self):
        """None の場合 True"""
        pm = self._make_pm()
        assert pm.check_caller_requires("caller_1", None) is True

    def test_permissive_auto_pass(self):
        """permissive モードでは全権限を自動パス"""
        pm = self._make_pm()
        assert pm.check_caller_requires("caller_1", ["file_read", "network", "exec"]) is True

    def test_caller_id_empty_string_returns_false(self):
        """caller_principal_id が空文字の場合 False"""
        pm = self._make_pm()
        assert pm.check_caller_requires("", ["file_read"]) is False

    def test_caller_id_none_returns_false(self):
        """caller_principal_id が None の場合 False"""
        pm = self._make_pm()
        assert pm.check_caller_requires(None, ["file_read"]) is False


class TestCheckCallerRequiresSecure:
    """secure モードのテスト"""

    def _make_pm(self):
        from core_runtime.permission_manager import PermissionManager
        return PermissionManager(mode="secure")

    def test_all_permissions_granted(self):
        """全権限を持つ場合 True"""
        pm = self._make_pm()
        pm.grant("caller_1", "file_read")
        pm.grant("caller_1", "network")
        assert pm.check_caller_requires("caller_1", ["file_read", "network"]) is True

    def test_one_permission_missing(self):
        """1つ権限が欠けている場合 False"""
        pm = self._make_pm()
        pm.grant("caller_1", "file_read")
        # network は付与しない
        assert pm.check_caller_requires("caller_1", ["file_read", "network"]) is False

    def test_all_permissions_missing(self):
        """全権限が欠けている場合 False"""
        pm = self._make_pm()
        assert pm.check_caller_requires("caller_1", ["file_read", "network"]) is False

    def test_secure_mode_no_permission(self):
        """secure モードで権限不足の場合 False"""
        pm = self._make_pm()
        assert pm.check_caller_requires("caller_1", ["exec"]) is False

    def test_single_permission_granted(self):
        """1つの権限のみ要求され、保有している場合 True"""
        pm = self._make_pm()
        pm.grant("caller_1", "file_read")
        assert pm.check_caller_requires("caller_1", ["file_read"]) is True

    def test_grant_then_check_becomes_true(self):
        """grant() で権限付与後に True になる"""
        pm = self._make_pm()
        # 付与前は False
        assert pm.check_caller_requires("caller_1", ["file_read"]) is False
        # 付与
        pm.grant("caller_1", "file_read")
        # 付与後は True
        assert pm.check_caller_requires("caller_1", ["file_read"]) is True


class TestCheckCallerRequiresEdgeCases:
    """エッジケースのテスト"""

    def test_caller_requires_not_list_returns_false(self):
        """caller_requires が list でない場合 False"""
        from core_runtime.permission_manager import PermissionManager
        pm = PermissionManager(mode="permissive")
        assert pm.check_caller_requires("caller_1", "file_read") is False
        assert pm.check_caller_requires("caller_1", 42) is False
        assert pm.check_caller_requires("caller_1", {"file_read": True}) is False
