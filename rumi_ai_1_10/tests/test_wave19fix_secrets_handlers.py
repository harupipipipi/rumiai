"""W19-FIX: secrets_handlers.py 欠落メソッドのテスト"""

import pytest
from unittest.mock import MagicMock, patch

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# --- テスト対象の Mixin を直接インスタンス化するヘルパー ---

def _make_handler(mock_mgr):
    """SecretsHandlersMixin のインスタンスを生成し、
    _get_secrets_grant_manager をモックに差し替える"""
    from core_runtime.api.secrets_handlers import SecretsHandlersMixin
    handler = SecretsHandlersMixin()
    return handler


@pytest.fixture
def mock_mgr():
    """SecretsGrantManager のモック"""
    mgr = MagicMock()
    mgr.get_granted_keys.return_value = ["API_KEY", "DB_PASSWORD"]
    mgr.delete_grant.return_value = True
    mgr.revoke_secret_access.return_value = True
    mgr.list_all_grants.return_value = {}
    return mgr


@pytest.fixture
def handler(mock_mgr):
    """SecretsHandlersMixin のインスタンス（モック注入済み）"""
    from core_runtime.api.secrets_handlers import SecretsHandlersMixin
    h = SecretsHandlersMixin()
    return h


# --- _secrets_grants_get_pack ---

class TestSecretsGrantsGetPack:

    def test_existing_pack_returns_granted_keys(self, mock_mgr):
        """存在する pack_id で Grant 情報が返る"""
        with patch("core_runtime.api.secrets_handlers._get_secrets_grant_manager", return_value=mock_mgr):
            from core_runtime.api.secrets_handlers import SecretsHandlersMixin
            h = SecretsHandlersMixin()
            result = h._secrets_grants_get_pack("test-pack-001")
        assert result["pack_id"] == "test-pack-001"
        assert result["granted_keys"] == ["API_KEY", "DB_PASSWORD"]
        assert result["count"] == 2
        assert "error" not in result

    def test_nonexistent_pack_returns_empty(self, mock_mgr):
        """存在しない pack_id は空リストを返す"""
        mock_mgr.get_granted_keys.return_value = []
        with patch("core_runtime.api.secrets_handlers._get_secrets_grant_manager", return_value=mock_mgr):
            from core_runtime.api.secrets_handlers import SecretsHandlersMixin
            h = SecretsHandlersMixin()
            result = h._secrets_grants_get_pack("nonexistent-pack")
        assert result["granted_keys"] == []
        assert result["count"] == 0
        assert "error" not in result

    def test_empty_pack_id_returns_error(self):
        """空の pack_id はエラーを返す"""
        from core_runtime.api.secrets_handlers import SecretsHandlersMixin
        h = SecretsHandlersMixin()
        result = h._secrets_grants_get_pack("")
        assert "error" in result
        assert "pack_id" in result["error"].lower() or "Missing" in result["error"]

    def test_exception_returns_safe_error(self, mock_mgr):
        """例外発生時はセーフなエラーメッセージを返す"""
        mock_mgr.get_granted_keys.side_effect = RuntimeError("DB down")
        with patch("core_runtime.api.secrets_handlers._get_secrets_grant_manager", return_value=mock_mgr):
            from core_runtime.api.secrets_handlers import SecretsHandlersMixin
            h = SecretsHandlersMixin()
            result = h._secrets_grants_get_pack("test-pack-001")
        assert "error" in result
        assert isinstance(result["error"], str)


# --- _secrets_grants_delete_pack ---

class TestSecretsGrantsDeletePack:

    def test_existing_grant_deleted(self, mock_mgr):
        """存在する Grant の削除に成功"""
        with patch("core_runtime.api.secrets_handlers._get_secrets_grant_manager", return_value=mock_mgr):
            from core_runtime.api.secrets_handlers import SecretsHandlersMixin
            h = SecretsHandlersMixin()
            result = h._secrets_grants_delete_pack("test-pack-001")
        assert result.get("success") is True
        assert result["pack_id"] == "test-pack-001"
        assert "error" not in result

    def test_nonexistent_grant_returns_error(self, mock_mgr):
        """存在しない Grant の削除はエラー（クラッシュしない）"""
        mock_mgr.delete_grant.return_value = False
        with patch("core_runtime.api.secrets_handlers._get_secrets_grant_manager", return_value=mock_mgr):
            from core_runtime.api.secrets_handlers import SecretsHandlersMixin
            h = SecretsHandlersMixin()
            result = h._secrets_grants_delete_pack("nonexistent-pack")
        assert "error" in result
        assert isinstance(result, dict)

    def test_empty_pack_id_returns_error(self):
        """空の pack_id はエラーを返す"""
        from core_runtime.api.secrets_handlers import SecretsHandlersMixin
        h = SecretsHandlersMixin()
        result = h._secrets_grants_delete_pack("")
        assert "error" in result


# --- _secrets_grants_delete_key ---

class TestSecretsGrantsDeleteKey:

    def test_existing_key_deleted(self, mock_mgr):
        """存在するキーの削除に成功"""
        with patch("core_runtime.api.secrets_handlers._get_secrets_grant_manager", return_value=mock_mgr):
            from core_runtime.api.secrets_handlers import SecretsHandlersMixin
            h = SecretsHandlersMixin()
            result = h._secrets_grants_delete_key("test-pack-001", "API_KEY")
        assert result.get("success") is True
        assert result["pack_id"] == "test-pack-001"
        assert result["revoked_key"] == "API_KEY"
        assert "error" not in result

    def test_nonexistent_key_returns_error(self, mock_mgr):
        """存在しないキーの削除はエラー（クラッシュしない）"""
        mock_mgr.revoke_secret_access.return_value = False
        with patch("core_runtime.api.secrets_handlers._get_secrets_grant_manager", return_value=mock_mgr):
            from core_runtime.api.secrets_handlers import SecretsHandlersMixin
            h = SecretsHandlersMixin()
            result = h._secrets_grants_delete_key("test-pack-001", "NONEXISTENT_KEY")
        assert "error" in result
        assert isinstance(result, dict)

    def test_empty_secret_key_returns_error(self, mock_mgr):
        """空の secret_key はエラーを返す"""
        with patch("core_runtime.api.secrets_handlers._get_secrets_grant_manager", return_value=mock_mgr):
            from core_runtime.api.secrets_handlers import SecretsHandlersMixin
            h = SecretsHandlersMixin()
            result = h._secrets_grants_delete_key("test-pack-001", "")
        assert "error" in result

    def test_empty_pack_id_returns_error(self):
        """空の pack_id はエラーを返す"""
        from core_runtime.api.secrets_handlers import SecretsHandlersMixin
        h = SecretsHandlersMixin()
        result = h._secrets_grants_delete_key("", "API_KEY")
        assert "error" in result


# --- 全メソッドが dict を返す（None でない）---

class TestAllMethodsReturnDict:

    def test_get_pack_returns_dict(self, mock_mgr):
        with patch("core_runtime.api.secrets_handlers._get_secrets_grant_manager", return_value=mock_mgr):
            from core_runtime.api.secrets_handlers import SecretsHandlersMixin
            h = SecretsHandlersMixin()
            result = h._secrets_grants_get_pack("test-pack")
        assert isinstance(result, dict)

    def test_delete_pack_returns_dict(self, mock_mgr):
        with patch("core_runtime.api.secrets_handlers._get_secrets_grant_manager", return_value=mock_mgr):
            from core_runtime.api.secrets_handlers import SecretsHandlersMixin
            h = SecretsHandlersMixin()
            result = h._secrets_grants_delete_pack("test-pack")
        assert isinstance(result, dict)

    def test_delete_key_returns_dict(self, mock_mgr):
        with patch("core_runtime.api.secrets_handlers._get_secrets_grant_manager", return_value=mock_mgr):
            from core_runtime.api.secrets_handlers import SecretsHandlersMixin
            h = SecretsHandlersMixin()
            result = h._secrets_grants_delete_key("test-pack", "KEY")
        assert isinstance(result, dict)


# --- 回帰テスト: _secrets_grants_list ---

class TestSecretsGrantsListRegression:

    def test_grants_list_returns_dict(self, mock_mgr):
        """既存メソッド _secrets_grants_list が引き続き動作する"""
        with patch("core_runtime.api.secrets_handlers._get_secrets_grant_manager", return_value=mock_mgr):
            from core_runtime.api.secrets_handlers import SecretsHandlersMixin
            h = SecretsHandlersMixin()
            result = h._secrets_grants_list()
        assert isinstance(result, dict)
        assert "grants" in result
        assert "count" in result
