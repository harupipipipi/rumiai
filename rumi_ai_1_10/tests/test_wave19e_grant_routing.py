"""
W19-E: Secret Grant ルーティング接続テスト

Part A — pack_api_server.py のソースを静的解析し、
         do_GET / do_POST / do_DELETE に Grant ルーティングが存在することを検証。
Part B — SecretsHandlersMixin の新メソッドを StubHandler 経由で呼び出し、
         MockGrantManager で結果を検証。

Note: core_runtime.paths に BASE_DIR が未定義のため、paths.py を
      経由するインポートチェーンを事前にダミー登録で迂回する。
"""
from __future__ import annotations

import re
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ======================================================================
# paths.py / security 系インポートチェーンの迂回
#
# core_runtime.api.__init__ → .security → capability_installer_handlers
# → ...paths (BASE_DIR 未定義で NameError)
# この問題を回避するため paths をダミーモジュールで先行登録する。
# ======================================================================
_PROJECT_ROOT = Path(__file__).resolve().parent.parent  # rumi_ai_1_10/
_CR_DIR = str(_PROJECT_ROOT / "core_runtime")

# --- core_runtime.paths ダミー ---
_dummy_paths = types.ModuleType("core_runtime.paths")
_dummy_paths.__file__ = _CR_DIR + "/paths.py"
_dummy_paths.BASE_DIR = _PROJECT_ROOT
_dummy_paths.ECOSYSTEM_DIR = str(_PROJECT_ROOT / "ecosystem")
_dummy_paths.OFFICIAL_FLOWS_DIR = str(_PROJECT_ROOT / "flows")
_dummy_paths.USER_SHARED_DIR = str(_PROJECT_ROOT / "user_data" / "shared")
_dummy_paths.USER_SHARED_FLOWS_DIR = str(_PROJECT_ROOT / "user_data" / "shared" / "flows")
_dummy_paths.USER_SHARED_MODIFIERS_DIR = str(
    _PROJECT_ROOT / "user_data" / "shared" / "flows" / "modifiers"
)
_dummy_paths.LOCAL_PACK_ID = "local_pack"
_dummy_paths.LOCAL_PACK_DIR = str(_PROJECT_ROOT / "ecosystem" / "flows")
_dummy_paths.LOCAL_PACK_MODIFIERS_DIR = str(
    _PROJECT_ROOT / "ecosystem" / "flows" / "modifiers"
)
_dummy_paths.GRANTS_DIR = str(_PROJECT_ROOT / "user_data" / "permissions")
_dummy_paths.PACK_DATA_BASE_DIR = str(_PROJECT_ROOT / "user_data" / "packs")
_dummy_paths.EXCLUDED_DIRS = frozenset()
_dummy_paths.LEGACY_PACKS_SUBDIR = "packs"
_dummy_paths.is_path_within = lambda target, boundary: True
_dummy_paths.discover_pack_locations = lambda *a, **kw: []
_dummy_paths.find_ecosystem_json = lambda *a, **kw: (None, None)
_dummy_paths.get_pack_flow_dirs = lambda *a, **kw: []
_dummy_paths.get_pack_modifier_dirs = lambda *a, **kw: []
_dummy_paths.get_pack_block_dirs = lambda *a, **kw: []
_dummy_paths.get_pack_lib_dirs = lambda *a, **kw: []
_dummy_paths.get_shared_flow_dir = lambda: Path(".")
_dummy_paths.get_shared_modifier_dir = lambda: Path(".")
_dummy_paths.check_pack_id_mismatch = lambda *a, **kw: None
sys.modules["core_runtime.paths"] = _dummy_paths

# ======================================================================
# pack_api_server.py のソースを読み込む (静的検証用)
# ======================================================================
_SERVER_PY = _PROJECT_ROOT / "core_runtime" / "pack_api_server.py"
_SERVER_SRC = _SERVER_PY.read_text(encoding="utf-8")


# ======================================================================
# validation.py から validate_pack_id を直接インポート
# ======================================================================
from core_runtime.validation import validate_pack_id


# ======================================================================
# SecretsHandlersMixin をインポート
# (paths.py はダミー登録済みなので api/__init__.py が通る)
# ======================================================================
from core_runtime.api.store.secrets_handlers import SecretsHandlersMixin


# ======================================================================
# Mock SecretGrant / MockGrantManager
# ======================================================================
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


# ======================================================================
# StubHandler
# ======================================================================
class StubHandler(SecretsHandlersMixin):
    pass


_PATCH = "core_runtime.api.store.secrets_handlers._w19e_get_secrets_grant_manager"


# ======================================================================
# Part A: ルーティング静的検証 (5 件)
# ======================================================================
class TestRoutingPatterns:
    """pack_api_server.py に正しいルーティングが存在する"""

    def _method_body(self, name: str) -> str:
        pat = rf"(    def {name}\(self\).*?)(?=\n    def |\nclass |\Z)"
        m = re.search(pat, _SERVER_SRC, re.DOTALL)
        assert m, f"{name} not found"
        return m.group(1)

    def test_get_grants_list_route(self):
        body = self._method_body("do_GET")
        assert 'path == "/api/secrets/grants"' in body

    def test_get_grants_pack_route(self):
        body = self._method_body("do_GET")
        assert 'path.startswith("/api/secrets/grants/")' in body

    def test_post_grants_route(self):
        body = self._method_body("do_POST")
        assert 'path.startswith("/api/secrets/grants/")' in body

    def test_delete_grants_route(self):
        body = self._method_body("do_DELETE")
        assert 'path.startswith("/api/secrets/grants/")' in body

    def test_delete_key_branch(self):
        body = self._method_body("do_DELETE")
        assert "_secrets_grants_delete_key" in body


# ======================================================================
# Part B: ハンドラメソッド動的テスト (11 件)
# ======================================================================
class TestGrantsList:
    @patch(_PATCH, return_value=_mock_mgr)
    def test_returns_grants(self, _m):
        _mock_mgr._grants["p1"] = MockSecretGrant("p1", ["K1"])
        r = StubHandler()._secrets_grants_list()
        assert "grants" in r and r["count"] >= 1
        _mock_mgr._grants.clear()


class TestGrantsGet:
    @patch(_PATCH, return_value=_mock_mgr)
    def test_existing(self, _m):
        _mock_mgr._grants["tp"] = MockSecretGrant("tp", ["K1", "K2"])
        r = StubHandler()._secrets_grants_get("tp")
        assert r["pack_id"] == "tp" and "K1" in r["granted_keys"]
        _mock_mgr._grants.clear()

    @patch(_PATCH, return_value=_mock_mgr)
    def test_nonexistent_empty(self, _m):
        _mock_mgr._grants.clear()
        r = StubHandler()._secrets_grants_get("ghost")
        assert r["granted_keys"] == []


class TestGrantsGrant:
    @patch(_PATCH, return_value=_mock_mgr)
    def test_normal(self, _m):
        r = StubHandler()._secrets_grants_grant("mp", {"secret_keys": ["API_KEY"]})
        assert r["success"] and "API_KEY" in r["granted_keys"]
        _mock_mgr._grants.clear()

    @patch(_PATCH, return_value=_mock_mgr)
    def test_empty_keys_400(self, _m):
        r = StubHandler()._secrets_grants_grant("mp", {"secret_keys": []})
        assert not r["success"] and r["status_code"] == 400

    @patch(_PATCH, return_value=_mock_mgr)
    def test_missing_keys_400(self, _m):
        r = StubHandler()._secrets_grants_grant("mp", {})
        assert not r["success"] and r["status_code"] == 400

    @patch(_PATCH, return_value=_mock_mgr)
    def test_invalid_format_400(self, _m):
        r = StubHandler()._secrets_grants_grant("mp", {"secret_keys": ["bad-key!"]})
        assert not r["success"] and r["status_code"] == 400


class TestGrantsDelete:
    @patch(_PATCH, return_value=_mock_mgr)
    def test_existing(self, _m):
        _mock_mgr._grants["d1"] = MockSecretGrant("d1", ["K"])
        r = StubHandler()._secrets_grants_delete("d1")
        assert r["success"]

    @patch(_PATCH, return_value=_mock_mgr)
    def test_nonexistent_404(self, _m):
        _mock_mgr._grants.clear()
        r = StubHandler()._secrets_grants_delete("nope")
        assert not r["success"] and r["status_code"] == 404


class TestGrantsDeleteKey:
    @patch(_PATCH, return_value=_mock_mgr)
    def test_specific_key(self, _m):
        _mock_mgr._grants["kp"] = MockSecretGrant("kp", ["K1", "K2"])
        r = StubHandler()._secrets_grants_delete_key("kp", "K1")
        assert r["success"] and r["revoked_key"] == "K1"
        _mock_mgr._grants.clear()


class TestPathTraversal:
    def test_dotdot_rejected(self):
        assert validate_pack_id("../etc") is False

    def test_encoded_rejected(self):
        assert validate_pack_id("..%2Ffoo") is False

    def test_valid_accepted(self):
        assert validate_pack_id("my-pack_01") is True
