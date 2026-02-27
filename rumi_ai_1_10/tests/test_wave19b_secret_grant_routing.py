"""
test_wave19b_secret_grant_routing.py

W19-B テスト:
  - Secret Grant ルーティング (13 件以上)
  - JSON ファイルサイズ上限 (5 件以上)
"""
from __future__ import annotations

import http.client
import json
import logging
import os
import sys
import tempfile
import threading
import time
from http.server import HTTPServer
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# conftest.py で core_runtime パッケージが登録されている前提
# ---------------------------------------------------------------------------


# ===================================================================
# Part 1: Secret Grant ルーティング テスト
# ===================================================================

def _find_free_port() -> int:
    """空きポートを見つける"""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def api_server(tmp_path):
    """
    テスト用 PackAPIServer をセットアップして起動する。

    SecretsGrantManager を tmp_path 配下で初期化し、
    HMACKeyManager もテスト用に初期化する。
    """
    # HMACKeyManager を tmp_path で初期化
    from core_runtime.hmac_key_manager import HMACKeyManager
    from core_runtime.di_container import get_container

    container = get_container()

    hmac_keys_path = str(tmp_path / "hmac_keys.json")
    hmac_mgr = HMACKeyManager(keys_path=hmac_keys_path)
    container.set_instance("hmac_key_manager", hmac_mgr)
    token = hmac_mgr.get_active_key()

    # SecretsGrantManager を tmp_path で初期化
    from core_runtime.secrets_grant_manager import SecretsGrantManager

    grants_dir = str(tmp_path / "grants")
    sgm = SecretsGrantManager(grants_dir=grants_dir, secret_key="test-secret-key-for-hmac-signing-32c")
    container.set_instance("secrets_grant_manager", sgm)

    # AuditLogger をモックで設定
    audit_mock = MagicMock()
    container.set_instance("audit_logger", audit_mock)

    # PackAPIHandler を直接構成してサーバーを起動
    from core_runtime.pack_api_server import PackAPIHandler

    port = _find_free_port()

    PackAPIHandler.approval_manager = None
    PackAPIHandler.container_orchestrator = None
    PackAPIHandler.host_privilege_manager = None
    PackAPIHandler.internal_token = token
    PackAPIHandler._hmac_key_manager = hmac_mgr
    PackAPIHandler.kernel = None
    PackAPIHandler._allowed_origins = None  # リセット

    # _match_pack_route をスタブ化（Pack独自ルートがないテスト環境で 404 を返すため）
    if not hasattr(PackAPIHandler, '_match_pack_route') or PackAPIHandler._match_pack_route is None:
        PackAPIHandler._match_pack_route = lambda self, path, method: None
    if not hasattr(PackAPIHandler, '_handle_pack_route_request'):
        PackAPIHandler._handle_pack_route_request = lambda self, *a, **kw: None

    server = HTTPServer(("127.0.0.1", port), PackAPIHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield {
        "host": "127.0.0.1",
        "port": port,
        "token": token,
        "sgm": sgm,
        "server": server,
    }

    server.shutdown()
    thread.join(timeout=5)


def _request(info, method, path, body=None, auth=True):
    """テスト用HTTPリクエストヘルパー"""
    conn = http.client.HTTPConnection(info["host"], info["port"], timeout=10)
    headers = {"Content-Type": "application/json"}
    if auth:
        headers["Authorization"] = f"Bearer {info['token']}"
    payload = json.dumps(body).encode("utf-8") if body else None
    conn.request(method, path, body=payload, headers=headers)
    resp = conn.getresponse()
    data = resp.read().decode("utf-8")
    conn.close()
    try:
        parsed = json.loads(data)
    except json.JSONDecodeError:
        parsed = {"raw": data}
    return resp.status, parsed


# --- 1. GET /api/secrets/grants — 認証あり → 200 + 一覧 ---
class TestSecretGrantRouting:

    def test_get_grants_list_authenticated(self, api_server):
        status, data = _request(api_server, "GET", "/api/secrets/grants")
        assert status == 200
        assert data["success"] is True
        assert "grants" in data["data"]

    # --- 2. GET /api/secrets/grants — 認証なし → 401 ---
    def test_get_grants_list_unauthenticated(self, api_server):
        status, data = _request(api_server, "GET", "/api/secrets/grants", auth=False)
        assert status == 401
        assert data["success"] is False

    # --- 3. GET /api/secrets/grants/{pack_id} — 存在する Pack → 200 ---
    def test_get_grant_existing_pack(self, api_server):
        # まず Grant を作成
        api_server["sgm"].grant_secret_access("test_pack", ["KEY1", "KEY2"])
        status, data = _request(api_server, "GET", "/api/secrets/grants/test_pack")
        assert status == 200
        assert data["success"] is True
        assert data["data"]["pack_id"] == "test_pack"
        assert data["data"]["grant"] is not None

    # --- 4. GET /api/secrets/grants/{pack_id} — 存在しない Pack → 200 + 空 ---
    def test_get_grant_nonexistent_pack(self, api_server):
        status, data = _request(api_server, "GET", "/api/secrets/grants/nonexistent")
        assert status == 200
        assert data["success"] is True
        assert data["data"]["grant"] is None

    # --- 5. POST /api/secrets/grants/{pack_id} — 正常な body → 200 ---
    def test_post_grant_success(self, api_server):
        status, data = _request(
            api_server, "POST", "/api/secrets/grants/mypack",
            body={"secret_keys": ["API_KEY", "DB_PASS"]}
        )
        assert status == 200
        assert data["success"] is True
        assert data["data"]["pack_id"] == "mypack"
        assert "API_KEY" in data["data"]["granted_keys"]

    # --- 6. POST /api/secrets/grants/{pack_id} — body なし → 400 ---
    def test_post_grant_no_body(self, api_server):
        status, data = _request(
            api_server, "POST", "/api/secrets/grants/mypack",
            body={}
        )
        assert status == 400
        assert data["success"] is False

    # --- 7. POST /api/secrets/grants/{pack_id} — secret_keys が空配列 → 400 ---
    def test_post_grant_empty_keys(self, api_server):
        status, data = _request(
            api_server, "POST", "/api/secrets/grants/mypack",
            body={"secret_keys": []}
        )
        assert status == 400
        assert data["success"] is False

    # --- 8. POST /api/secrets/grants/{pack_id} — 認証なし → 401 ---
    def test_post_grant_unauthenticated(self, api_server):
        status, data = _request(
            api_server, "POST", "/api/secrets/grants/mypack",
            body={"secret_keys": ["KEY1"]},
            auth=False,
        )
        assert status == 401
        assert data["success"] is False

    # --- 9. DELETE /api/secrets/grants/{pack_id} — 存在する Grant → 200 ---
    def test_delete_grant_existing(self, api_server):
        api_server["sgm"].grant_secret_access("del_pack", ["KEY1"])
        status, data = _request(api_server, "DELETE", "/api/secrets/grants/del_pack")
        assert status == 200
        assert data["success"] is True

    # --- 10. DELETE /api/secrets/grants/{pack_id} — 存在しない Grant → 404 ---
    def test_delete_grant_nonexistent(self, api_server):
        status, data = _request(api_server, "DELETE", "/api/secrets/grants/no_such_pack")
        assert status == 404

    # --- 11. DELETE /api/secrets/grants/{pack_id}/{secret_key} — 特定キー削除 → 200 ---
    def test_delete_grant_specific_key(self, api_server):
        api_server["sgm"].grant_secret_access("key_pack", ["KEY1", "KEY2"])
        status, data = _request(api_server, "DELETE", "/api/secrets/grants/key_pack/KEY1")
        assert status == 200
        assert data["success"] is True
        # KEY2 はまだ残っている
        remaining = api_server["sgm"].get_granted_keys("key_pack")
        assert "KEY1" not in remaining
        assert "KEY2" in remaining

    # --- 12. DELETE /api/secrets/grants/{pack_id}/{secret_key} — 認証なし → 401 ---
    def test_delete_grant_key_unauthenticated(self, api_server):
        status, data = _request(
            api_server, "DELETE", "/api/secrets/grants/key_pack/KEY1",
            auth=False,
        )
        assert status == 401
        assert data["success"] is False

    # --- 13. pack_id にパストラバーサル文字を含む → 400 ---
    def test_path_traversal_pack_id(self, api_server):
        status, data = _request(api_server, "GET", "/api/secrets/grants/../etc/passwd")
        # _validate_pack_id は ../etc/passwd を拒否する（PACK_ID_RE に合致しない）
        # ただし URL パース上 /api/secrets/grants/../etc/passwd は
        # /api/secrets/etc/passwd に正規化される可能性がある。
        # 明示的に pack_id = "../bad" のケースも確認
        status2, data2 = _request(api_server, "POST", "/api/secrets/grants/..%2F..%2Fetc",
                                   body={"secret_keys": ["KEY1"]})
        assert status2 == 400
        assert data2["success"] is False

    # --- 14. POST で不正な secret_key を含む → 400 ---
    def test_post_grant_invalid_key_format(self, api_server):
        status, data = _request(
            api_server, "POST", "/api/secrets/grants/mypack",
            body={"secret_keys": ["invalid-key!"]}
        )
        assert status == 400
        assert data["success"] is False


# ===================================================================
# Part 2: JSON ファイルサイズ上限テスト
# ===================================================================

class TestJsonFileSizeLimit:

    def test_normal_size_json_loads_ok(self, tmp_path):
        """正常サイズの JSON は正常に読み込まれる"""
        from backend_core.ecosystem.registry import _check_json_file_size

        f = tmp_path / "small.json"
        f.write_text('{"key": "value"}', encoding="utf-8")
        assert _check_json_file_size(f) is True

    def test_oversized_json_skipped(self, tmp_path):
        """上限超過の JSON は WARNING + スキップ"""
        from backend_core.ecosystem.registry import _check_json_file_size

        f = tmp_path / "big.json"
        # デフォルト 2MB を超えるファイルを作成
        f.write_bytes(b"x" * (2 * 1024 * 1024 + 1))
        assert _check_json_file_size(f) is False

    def test_custom_limit_via_env(self, tmp_path, monkeypatch):
        """RUMI_MAX_JSON_FILE_BYTES でカスタム上限設定"""
        from backend_core.ecosystem.registry import _check_json_file_size

        monkeypatch.setenv("RUMI_MAX_JSON_FILE_BYTES", "100")
        f = tmp_path / "medium.json"
        f.write_bytes(b"x" * 101)
        assert _check_json_file_size(f) is False

        f2 = tmp_path / "small.json"
        f2.write_bytes(b"x" * 50)
        assert _check_json_file_size(f2) is True

    def test_zero_byte_json(self, tmp_path):
        """0 バイトの JSON ファイルはサイズチェックは通過（json.load でエラーになるのは別の問題）"""
        from backend_core.ecosystem.registry import _check_json_file_size

        f = tmp_path / "empty.json"
        f.write_text("", encoding="utf-8")
        # 0 バイトは上限超過ではないのでTrue
        assert _check_json_file_size(f) is True

    def test_exact_limit_json_loads_ok(self, tmp_path, monkeypatch):
        """上限ちょうどの JSON は正常読み込み"""
        from backend_core.ecosystem.registry import _check_json_file_size

        monkeypatch.setenv("RUMI_MAX_JSON_FILE_BYTES", "200")
        f = tmp_path / "exact.json"
        f.write_bytes(b"x" * 200)
        assert _check_json_file_size(f) is True

    def test_one_over_limit_json_skipped(self, tmp_path, monkeypatch):
        """上限を1バイト超えた JSON はスキップ"""
        from backend_core.ecosystem.registry import _check_json_file_size

        monkeypatch.setenv("RUMI_MAX_JSON_FILE_BYTES", "200")
        f = tmp_path / "over.json"
        f.write_bytes(b"x" * 201)
        assert _check_json_file_size(f) is False

    def test_nonexistent_file_returns_false(self, tmp_path):
        """存在しないファイルは False"""
        from backend_core.ecosystem.registry import _check_json_file_size

        f = tmp_path / "nonexistent.json"
        assert _check_json_file_size(f) is False

    def test_invalid_env_value_uses_default(self, tmp_path, monkeypatch):
        """不正な環境変数値はデフォルトにフォールバック"""
        from backend_core.ecosystem.registry import _get_max_json_file_bytes

        monkeypatch.setenv("RUMI_MAX_JSON_FILE_BYTES", "not_a_number")
        assert _get_max_json_file_bytes() == 2 * 1024 * 1024
