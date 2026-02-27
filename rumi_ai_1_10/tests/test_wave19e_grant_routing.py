"""
W19-E: Secret Grant ルーティング接続テスト

Part A — pack_api_server.py のソースコードを読み、
         do_GET / do_POST / do_DELETE に Grant ルーティングが
         正しく挿入されていることを静的に検証する。
Part B — SecretsHandlersMixin の新メソッドを StubHandler 経由で
         直接呼び出し、MockGrantManager で結果を検証する。
"""
from __future__ import annotations

import re
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# pack_api_server.py のソースを読み込む (静的検証用)
# ---------------------------------------------------------------------------
_SERVER_PY = (
    Path(__file__).resolve().parent.parent
    / "core_runtime"
    / "pack_api_server.py"
)
_SERVER_SRC = _SERVER_PY.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# validation.py から validate_pack_id を直接インポート
# (paths.py を経由しないので安全)
# ---------------------------------------------------------------------------
from core_runtime.validation import validate_pack_id


# ---------------------------------------------------------------------------
# SecretsHandlersMixin を直接インポート
# (store パッケージは paths.py に依存しない)
# ---------------------------------------------------------------------------
from core_runtime.api.store.secrets_handlers import SecretsHandlersMixin


# ---------------------------------------------------------------------------
# Mock SecretGrant
# ---------------------------------------------------------------------------
class MockSecretGrant:
    def __init__(self, pack_id, granted_keys):
        self.pack_id = pack_id
        self.granted_keys = list(granted_keys)

    def to_dict(self):
        return {
            "pack_id": self.pack_id,
            "granted_keys": self.granted_keys,
            "granted_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "granted_by": "user",
        }


# ---------------------------------------------------------------------------
# Mock SecretsGrantManager
# ---------------------------------------------------------------------------
class MockGrantManager:
    def __init__(self):
        self._grants: dict[str, MockSecretGrant] = {}

    def list_all_grants(self):
        return dict(self._grants)

    def get_granted_keys(self, pack_id):
        g = self._grants.get(pack_id)
        return list(g.granted_keys) if g else []

    def grant_secret_access(self, pack_id, secret_keys, granted_by="user"):
        g = MockSecretGrant(pack_id, secret_keys)
        self._grants[pack_id] = g
        return g

    def delete_grant(self, pack_id):
        if pack_id in self._grants:
            del self._grants[pack_id]
            return True
        return False

    def revoke_secret_access(self, pack_id, secret_keys):
        g = self._grants.get(pack_id)
        if g:
            g.granted_keys = [k for k in g.granted_keys if k not in secret_keys]
            return True
        return False


_mock_mgr = MockGrantManager()


# ---------------------------------------------------------------------------
# StubHandler (test_flow_handlers.py と同じパターン)
# ---------------------------------------------------------------------------
class StubHandler(SecretsHandlersMixin):
    """SecretsHandlersMixin を利用するための最小スタブ"""
    pass


_PATCH_TARGET = (
    "core_runtime.api.store.secrets_handlers._w19e_get_secrets_grant_manager"
)


# ======================================================================
# Part A: ルーティング静的検証 (5 件)
# ======================================================================

class TestRoutingPatterns:
    """pack_api_server.py に正しいルーティングが挿入されていることを確認"""

    def _in_method(self, method_name: str) -> str:
        """do_GET / do_POST / do_DELETE のメソッド本文を抽出"""
        pattern = rf"(    def {method_name}\(self\).*?)(?=\n    def |\nclass |\Z)"
        m = re.search(pattern, _SERVER_SRC, re.DOTALL)
        assert m, f"{method_name} not found in pack_api_server.py"
        return m.group(1)

    def test_do_get_has_grants_list_route(self):
        """do_GET に /api/secrets/grants 完全一致ルートがある"""
        body = self._in_method("do_GET")
        assert 'path == "/api/secrets/grants"' in body

    def test_do_get_has_grants_pack_route(self):
        """do_GET に /api/secrets/grants/ prefix ルートがある"""
        body = self._in_method("do_GET")
        assert 'path.startswith("/api/secrets/grants/")' in body

    def test_do_post_has_grants_route(self):
        """do_POST に /api/secrets/grants/ prefix ルートがある"""
        body = self._in_method("do_POST")
        assert 'path.startswith("/api/secrets/grants/")' in body

    def test_do_delete_has_grants_route(self):
        """do_DELETE に /api/secrets/grants/ prefix ルートがある"""
        body = self._in_method("do_DELETE")
        assert 'path.startswith("/api/secrets/grants/")' in body

    def test_do_delete_handles_key_deletion(self):
        """do_DELETE に parts==5 (キー個別削除) ブランチがある"""
        body = self._in_method("do_DELETE")
        assert "_secrets_grants_delete_key" in body


# ======================================================================
# Part B: ハンドラメソッド動的テスト (11 件)
# ======================================================================

class TestSecretsGrantsList:
    """_secrets_grants_list"""

    @patch(_PATCH_TARGET, return_value=_mock_mgr)
    def test_list_returns_grants(self, _m):
        _mock_mgr._grants["p1"] = MockSecretGrant("p1", ["K1"])
        handler = StubHandler()
        result = handler._secrets_grants_list()
        assert "grants" in result
        assert result["count"] >= 1
        _mock_mgr._grants.clear()


class TestSecretsGrantsGet:
    """_secrets_grants_get"""

    @patch(_PATCH_TARGET, return_value=_mock_mgr)
    def test_existing_pack(self, _m):
        _mock_mgr._grants["tp"] = MockSecretGrant("tp", ["K1", "K2"])
        handler = StubHandler()
        result = handler._secrets_grants_get("tp")
        assert result["pack_id"] == "tp"
        assert "K1" in result["granted_keys"]
        _mock_mgr._grants.clear()

    @patch(_PATCH_TARGET, return_value=_mock_mgr)
    def test_nonexistent_pack_returns_empty(self, _m):
        _mock_mgr._grants.clear()
        handler = StubHandler()
        result = handler._secrets_grants_get("ghost")
        assert result["granted_keys"] == []


class TestSecretsGrantsGrant:
    """_secrets_grants_grant"""

    @patch(_PATCH_TARGET, return_value=_mock_mgr)
    def test_normal_grant(self, _m):
        handler = StubHandler()
        result = handler._secrets_grants_grant("mp", {"secret_keys": ["API_KEY"]})
        assert result["success"] is True
        assert "API_KEY" in result["granted_keys"]
        _mock_mgr._grants.clear()

    @patch(_PATCH_TARGET, return_value=_mock_mgr)
    def test_empty_keys_returns_400(self, _m):
        handler = StubHandler()
        result = handler._secrets_grants_grant("mp", {"secret_keys": []})
        assert result["success"] is False
        assert result["status_code"] == 400

    @patch(_PATCH_TARGET, return_value=_mock_mgr)
    def test_missing_keys_returns_400(self, _m):
        handler = StubHandler()
        result = handler._secrets_grants_grant("mp", {})
        assert result["success"] is False
        assert result["status_code"] == 400

    @patch(_PATCH_TARGET, return_value=_mock_mgr)
    def test_invalid_key_format_returns_400(self, _m):
        handler = StubHandler()
        result = handler._secrets_grants_grant("mp", {"secret_keys": ["bad-key!"]})
        assert result["success"] is False
        assert result["status_code"] == 400


class TestSecretsGrantsDelete:
    """_secrets_grants_delete"""

    @patch(_PATCH_TARGET, return_value=_mock_mgr)
    def test_delete_existing(self, _m):
        _mock_mgr._grants["del1"] = MockSecretGrant("del1", ["K"])
        handler = StubHandler()
        result = handler._secrets_grants_delete("del1")
        assert result["success"] is True

    @patch(_PATCH_TARGET, return_value=_mock_mgr)
    def test_delete_nonexistent_returns_404(self, _m):
        _mock_mgr._grants.clear()
        handler = StubHandler()
        result = handler._secrets_grants_delete("nope")
        assert result["success"] is False
        assert result["status_code"] == 404


class TestSecretsGrantsDeleteKey:
    """_secrets_grants_delete_key"""

    @patch(_PATCH_TARGET, return_value=_mock_mgr)
    def test_delete_specific_key(self, _m):
        _mock_mgr._grants["kp"] = MockSecretGrant("kp", ["K1", "K2"])
        handler = StubHandler()
        result = handler._secrets_grants_delete_key("kp", "K1")
        assert result["success"] is True
        assert result["revoked_key"] == "K1"
        _mock_mgr._grants.clear()


class TestPathTraversal:
    """pack_id に ../ が含まれる場合 validate_pack_id が False"""

    def test_traversal_rejected(self):
        assert validate_pack_id("../etc") is False

    def test_dot_dot_slash_rejected(self):
        assert validate_pack_id("..%2Ffoo") is False

    def test_valid_id_accepted(self):
        assert validate_pack_id("my-pack_01") is True
