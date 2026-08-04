"""Secret grant routes plus v4 artifact integrity (no legacy Registry scan)."""

from __future__ import annotations

import http.client
import json
import socket
import threading
from http.server import HTTPServer
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ecosystem.defaultspack.domain.runtime_v4 import BundleIntegrityError, BundledCatalog
from tests.v4_batch_support import assert_legacy_registry_fails_closed


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "ecosystem" / "defaultspack" / "v4"


def _find_free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture()
def api_server(tmp_path):
    from core_runtime.di_container import get_container
    from core_runtime.hmac_key_manager import HMACKeyManager
    from core_runtime.pack_api_server import PackAPIHandler
    from core_runtime.secrets_grant_manager import SecretsGrantManager

    container = get_container()
    hmac_manager = HMACKeyManager(keys_path=str(tmp_path / "hmac.json"))
    container.set_instance("hmac_key_manager", hmac_manager)
    grants = SecretsGrantManager(
        grants_dir=str(tmp_path / "grants"),
        secret_key="test-secret-key-for-hmac-signing-32c",
    )
    container.set_instance("secrets_grant_manager", grants)
    container.set_instance("audit_logger", MagicMock())
    PackAPIHandler.approval_manager = None
    PackAPIHandler.container_orchestrator = None
    PackAPIHandler.host_privilege_manager = None
    PackAPIHandler.internal_token = hmac_manager.get_active_key()
    PackAPIHandler._hmac_key_manager = hmac_manager
    PackAPIHandler.kernel = None
    PackAPIHandler._allowed_origins = None
    port = _find_free_port()
    server = HTTPServer(("127.0.0.1", port), PackAPIHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield {"host": "127.0.0.1", "port": port, "token": PackAPIHandler.internal_token, "sgm": grants}
    server.shutdown()
    thread.join(timeout=5)


def _request(info, method: str, path: str, body=None, auth: bool = True):
    connection = http.client.HTTPConnection(info["host"], info["port"], timeout=10)
    headers = {"Content-Type": "application/json"}
    if auth:
        headers["Authorization"] = f"Bearer {info['token']}"
    connection.request(
        method,
        path,
        body=json.dumps(body).encode("utf-8") if body is not None else None,
        headers=headers,
    )
    response = connection.getresponse()
    payload = response.read().decode("utf-8")
    connection.close()
    return response.status, json.loads(payload)


class TestSecretGrantRouting:
    def test_get_grants_list_authenticated(self, api_server):
        status, data = _request(api_server, "GET", "/api/secrets/grants")
        assert status == 200 and data["success"] is True

    def test_get_grants_list_unauthenticated(self, api_server):
        status, data = _request(api_server, "GET", "/api/secrets/grants", auth=False)
        assert status == 401 and data["success"] is False

    def test_get_grant_existing_pack(self, api_server):
        api_server["sgm"].grant_secret_access("test_pack", ["KEY1", "KEY2"])
        status, data = _request(api_server, "GET", "/api/secrets/grants/test_pack")
        assert status == 200 and data["data"]["pack_id"] == "test_pack"

    def test_get_grant_nonexistent_pack(self, api_server):
        status, data = _request(api_server, "GET", "/api/secrets/grants/missing")
        assert status == 200 and data["data"]["grant"] is None

    def test_post_grant_success(self, api_server):
        status, data = _request(
            api_server,
            "POST",
            "/api/secrets/grants/mypack",
            {"secret_keys": ["API_KEY", "DB_PASS"]},
        )
        assert status == 200 and "API_KEY" in data["data"]["granted_keys"]

    @pytest.mark.parametrize("body", [{}, {"secret_keys": []}])
    def test_post_grant_invalid_body(self, api_server, body):
        status, data = _request(api_server, "POST", "/api/secrets/grants/mypack", body)
        assert status == 400 and data["success"] is False

    def test_post_grant_unauthenticated(self, api_server):
        status, data = _request(
            api_server,
            "POST",
            "/api/secrets/grants/mypack",
            {"secret_keys": ["KEY1"]},
            auth=False,
        )
        assert status == 401 and data["success"] is False

    def test_delete_grant_existing(self, api_server):
        api_server["sgm"].grant_secret_access("del_pack", ["KEY1"])
        status, data = _request(api_server, "DELETE", "/api/secrets/grants/del_pack")
        assert status == 200 and data["success"] is True

    def test_delete_grant_nonexistent(self, api_server):
        status, _data = _request(api_server, "DELETE", "/api/secrets/grants/no_such_pack")
        assert status == 404

    def test_delete_grant_specific_key(self, api_server):
        api_server["sgm"].grant_secret_access("key_pack", ["KEY1", "KEY2"])
        status, _data = _request(api_server, "DELETE", "/api/secrets/grants/key_pack/KEY1")
        assert status == 200
        assert api_server["sgm"].get_granted_keys("key_pack") == ["KEY2"]

    def test_delete_grant_key_unauthenticated(self, api_server):
        status, data = _request(api_server, "DELETE", "/api/secrets/grants/key_pack/KEY1", auth=False)
        assert status == 401 and data["success"] is False

    def test_pack_id_traversal_is_rejected(self, api_server):
        status, data = _request(
            api_server,
            "POST",
            "/api/secrets/grants/..%2F..%2Fetc",
            {"secret_keys": ["KEY1"]},
        )
        assert status == 400 and data["success"] is False

    def test_secret_key_format_is_validated(self, api_server):
        status, data = _request(
            api_server,
            "POST",
            "/api/secrets/grants/mypack",
            {"secret_keys": ["invalid-key!"]},
        )
        assert status == 400 and data["success"] is False


def test_legacy_registry_json_scan_fails_closed() -> None:
    assert_legacy_registry_fails_closed()


def test_v4_catalog_has_hashed_artifacts() -> None:
    catalog = BundledCatalog.load(BUNDLE)
    assert all(item["pack"]["artifact_digest"].startswith("sha256:") for item in catalog.packs.values())


def test_v4_catalog_rejects_manifest_drift(tmp_path: Path) -> None:
    import shutil

    copied = tmp_path / "v4"
    shutil.copytree(BUNDLE, copied)
    manifest = copied / "packs" / "defaultspack.pack.v4.json"
    manifest.write_text(manifest.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(BundleIntegrityError, match="digest changed"):
        BundledCatalog.load(copied)
