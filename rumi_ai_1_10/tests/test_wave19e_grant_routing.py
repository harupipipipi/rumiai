"""
W19-E: Secret Grant ルーティング接続テスト

pack_api_server.py の do_GET / do_POST / do_DELETE に
Secret Grant エンドポイントが正しく接続されていることを検証する。

テスト方式:
  PackAPIHandler をスタブ化し、実際の HTTP サーバーを起動。
  urllib でリクエストを送信してステータスコードとレスポンスボディを検証。
"""
from __future__ import annotations

import json
import socket
import threading
from http.server import HTTPServer
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Mock SecretGrant
# ---------------------------------------------------------------------------
class MockSecretGrant:
    def __init__(self, pack_id, granted_keys):
        self.pack_id = pack_id
        self.granted_keys = list(granted_keys)
        self.granted_at = "2026-01-01T00:00:00Z"
        self.updated_at = "2026-01-01T00:00:00Z"
        self.granted_by = "user"

    def to_dict(self):
        return {
            "pack_id": self.pack_id,
            "granted_keys": self.granted_keys,
            "granted_at": self.granted_at,
            "updated_at": self.updated_at,
            "granted_by": self.granted_by,
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
# Import PackAPIHandler (conftest.py が core_runtime を登録済み)
# ---------------------------------------------------------------------------
from core_runtime.pack_api_server import PackAPIHandler  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture: テスト用 HTTP サーバー
# ---------------------------------------------------------------------------
def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def api():
    port = _free_port()
    token = "test-token-w19e"

    # クラス変数を直接設定
    PackAPIHandler.internal_token = token
    PackAPIHandler._hmac_key_manager = None
    PackAPIHandler.approval_manager = MagicMock()
    PackAPIHandler.container_orchestrator = MagicMock()
    PackAPIHandler.host_privilege_manager = MagicMock()
    PackAPIHandler.kernel = None
    PackAPIHandler._allowed_origins = None

    srv = HTTPServer(("127.0.0.1", port), PackAPIHandler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield {"port": port, "token": token}
    srv.shutdown()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
import urllib.request
import urllib.error


def _req(api, method, path, body=None, auth=True):
    url = f"http://127.0.0.1:{api['port']}{path}"
    data = json.dumps(body).encode() if body is not None else None
    hdrs = {"Content-Type": "application/json"}
    if auth:
        hdrs["Authorization"] = f"Bearer {api['token']}"
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}


# ===========================================================================
# テストケース
# ===========================================================================

_PATCH_TARGET = (
    "core_runtime.api.store.secrets_handlers._w19e_get_secrets_grant_manager"
)


class TestGetGrantsList:
    """GET /api/secrets/grants"""

    @patch(_PATCH_TARGET, return_value=_mock_mgr)
    def test_authenticated_200(self, _m, api):
        code, body = _req(api, "GET", "/api/secrets/grants")
        assert code == 200
        assert body.get("success") is True

    def test_unauthenticated_401(self, api):
        code, body = _req(api, "GET", "/api/secrets/grants", auth=False)
        assert code == 401
        assert body.get("success") is False


class TestGetGrantByPackId:
    """GET /api/secrets/grants/{pack_id}"""

    @patch(_PATCH_TARGET, return_value=_mock_mgr)
    def test_existing_pack_200(self, _m, api):
        _mock_mgr._grants["testpack"] = MockSecretGrant("testpack", ["KEY1", "KEY2"])
        code, body = _req(api, "GET", "/api/secrets/grants/testpack")
        assert code == 200
        assert body["success"] is True
        assert "KEY1" in body["data"]["granted_keys"]
        _mock_mgr._grants.pop("testpack", None)

    @patch(_PATCH_TARGET, return_value=_mock_mgr)
    def test_nonexistent_pack_200_empty(self, _m, api):
        _mock_mgr._grants.pop("ghost", None)
        code, body = _req(api, "GET", "/api/secrets/grants/ghost")
        assert code == 200
        assert body["success"] is True
        assert body["data"]["granted_keys"] == []


class TestPostGrant:
    """POST /api/secrets/grants/{pack_id}"""

    @patch(_PATCH_TARGET, return_value=_mock_mgr)
    def test_normal_body_200(self, _m, api):
        code, body = _req(
            api, "POST", "/api/secrets/grants/mypack",
            body={"secret_keys": ["API_KEY"]},
        )
        assert code == 200
        assert body["success"] is True
        _mock_mgr._grants.pop("mypack", None)

    @patch(_PATCH_TARGET, return_value=_mock_mgr)
    def test_no_body_400(self, _m, api):
        code, body = _req(
            api, "POST", "/api/secrets/grants/mypack",
            body={},
        )
        assert code == 400

    @patch(_PATCH_TARGET, return_value=_mock_mgr)
    def test_empty_keys_400(self, _m, api):
        code, body = _req(
            api, "POST", "/api/secrets/grants/mypack",
            body={"secret_keys": []},
        )
        assert code == 400

    def test_unauthenticated_401(self, api):
        code, _ = _req(
            api, "POST", "/api/secrets/grants/mypack",
            body={"secret_keys": ["K"]}, auth=False,
        )
        assert code == 401


class TestDeleteGrant:
    """DELETE /api/secrets/grants/{pack_id}"""

    @patch(_PATCH_TARGET, return_value=_mock_mgr)
    def test_existing_grant_200(self, _m, api):
        _mock_mgr._grants["delme"] = MockSecretGrant("delme", ["K1"])
        code, body = _req(api, "DELETE", "/api/secrets/grants/delme")
        assert code == 200
        assert body["success"] is True

    @patch(_PATCH_TARGET, return_value=_mock_mgr)
    def test_nonexistent_grant_404(self, _m, api):
        _mock_mgr._grants.pop("nope", None)
        code, body = _req(api, "DELETE", "/api/secrets/grants/nope")
        assert code == 404


class TestDeleteGrantKey:
    """DELETE /api/secrets/grants/{pack_id}/{secret_key}"""

    @patch(_PATCH_TARGET, return_value=_mock_mgr)
    def test_specific_key_200(self, _m, api):
        _mock_mgr._grants["kp"] = MockSecretGrant("kp", ["K1", "K2"])
        code, body = _req(api, "DELETE", "/api/secrets/grants/kp/K1")
        assert code == 200
        assert body["success"] is True

    def test_unauthenticated_401(self, api):
        code, _ = _req(
            api, "DELETE", "/api/secrets/grants/kp/K1", auth=False,
        )
        assert code == 401


class TestPathTraversal:
    """pack_id に ../ → 400"""

    def test_traversal_get_400(self, api):
        code, _ = _req(api, "GET", "/api/secrets/grants/..%2F..%2Fetc")
        assert code == 400

    @patch(_PATCH_TARGET, return_value=_mock_mgr)
    def test_traversal_post_400(self, _m, api):
        code, _ = _req(
            api, "POST", "/api/secrets/grants/..%2Ffoo",
            body={"secret_keys": ["K"]},
        )
        assert code == 400

    def test_traversal_delete_400(self, api):
        code, _ = _req(api, "DELETE", "/api/secrets/grants/..%2Fbar")
        assert code == 400
