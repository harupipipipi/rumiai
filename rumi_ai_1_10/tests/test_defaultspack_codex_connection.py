from __future__ import annotations

import json
import os
import secrets
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def _text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _fresh_token() -> str:
    return f"codex-{secrets.token_urlsafe(24)}"


def test_codex_token_status_and_route_responses_redact_raw_token():
    from blocks.connections import codex as codex_block
    from domain.codex.connection_store import codex_connection_status, save_codex_access_token

    with tempfile.TemporaryDirectory() as tmpdir:
        pack_root = Path(tmpdir)
        secrets_dir = pack_root / "user_data" / "secrets"
        token = _fresh_token()
        env = {
            "RUMI_DEFAULTSPACK_SECRETS_DIR": str(secrets_dir),
            "RUMI_CODEX_ACCESS_TOKEN": "",
            "CODEX_ACCESS_TOKEN": "",
        }
        with patch.dict(os.environ, env, clear=False):
            saved = save_codex_access_token(token, pack_root=pack_root)
            status = codex_connection_status(pack_root=pack_root)
            routed = codex_block.run(
                {"_method": "POST", "action": "save_token", "access_token": token},
                {},
            )

            assert saved["success"] is True
            assert status["configured"] is True
            assert routed["status"] == "ok"
            assert token not in _text(saved)
            assert token not in _text(status)
            assert token not in _text(routed)
            for path in secrets_dir.rglob("*"):
                if path.is_file():
                    assert token not in path.read_text(encoding="utf-8", errors="ignore")


def test_codex_app_server_remote_endpoint_requires_app_server_auth_not_codex_token():
    from domain.codex.app_server import codex_app_server_status, save_codex_app_server_config
    from domain.codex.connection_store import save_codex_access_token

    with tempfile.TemporaryDirectory() as tmpdir:
        pack_root = Path(tmpdir)
        secrets_dir = pack_root / "user_data" / "secrets"
        token = _fresh_token()
        app_secret = _fresh_token()
        env = {
            "RUMI_DEFAULTSPACK_SECRETS_DIR": str(secrets_dir),
            "RUMI_CODEX_ACCESS_TOKEN": "",
            "CODEX_ACCESS_TOKEN": "",
            "RUMI_CODEX_APP_SERVER_WS_TOKEN": "",
            "RUMI_CODEX_APP_SERVER_SHARED_SECRET": "",
        }
        with patch.dict(os.environ, env, clear=False):
            saved_without_app_auth = save_codex_app_server_config(
                {
                    "enabled": True,
                    "base_url": "https://codex-app.example.test",
                    "tool_source_enabled": True,
                    "automation_endpoint_enabled": True,
                },
                pack_root=pack_root,
            )
            save_codex_access_token(token, pack_root=pack_root)
            status_with_only_codex_token = codex_app_server_status(pack_root=pack_root)
        with patch.dict(os.environ, {**env, "RUMI_CODEX_APP_SERVER_WS_TOKEN": app_secret}, clear=False):
            saved_with_app_auth = save_codex_app_server_config(
                {
                    "enabled": True,
                    "transport": "websocket_remote",
                    "base_url": "https://codex-app.example.test",
                    "websocket_url": "wss://codex-app.example.test/ws",
                    "tool_source_enabled": True,
                    "automation_endpoint_enabled": True,
                },
                pack_root=pack_root,
            )
            status = codex_app_server_status(pack_root=pack_root)

    assert saved_without_app_auth["success"] is True
    assert saved_without_app_auth["app_server"]["connection_status"] == "blocked_auth_required"
    assert status_with_only_codex_token["connection_status"] == "blocked_auth_required"
    assert status_with_only_codex_token["auth_configured"] is False
    assert saved_with_app_auth["success"] is True
    assert status["auth_required"] is True
    assert status["auth_configured"] is True
    assert status["auth_source"] == "environment"
    assert status["auth_kind"] == "ws_token"
    assert token not in _text(saved_with_app_auth)
    assert token not in _text(status)
    assert app_secret not in _text(saved_with_app_auth)
    assert app_secret not in _text(status)


def test_codex_app_server_rejects_transport_url_mismatch_even_with_app_server_auth():
    from domain.codex.app_server import (
        build_codex_app_server_command,
        codex_app_server_probe,
        codex_app_server_status,
        save_codex_app_server_config,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        pack_root = Path(tmpdir)
        secrets_dir = pack_root / "user_data" / "secrets"
        app_secret = _fresh_token()
        env = {
            "RUMI_DEFAULTSPACK_SECRETS_DIR": str(secrets_dir),
            "RUMI_CODEX_ACCESS_TOKEN": "",
            "CODEX_ACCESS_TOKEN": "",
            "RUMI_CODEX_APP_SERVER_WS_TOKEN": app_secret,
            "RUMI_CODEX_APP_SERVER_SHARED_SECRET": "",
        }
        config = {
            "enabled": True,
            "transport": "websocket_loopback",
            "base_url": "https://codex-app.example.test",
            "websocket_url": "wss://codex-app.example.test/ws",
            "tool_source_enabled": True,
            "automation_endpoint_enabled": True,
        }
        with patch.dict(os.environ, env, clear=False):
            saved = save_codex_app_server_config(config, pack_root=pack_root)
            status = codex_app_server_status(pack_root=pack_root)
            probe = codex_app_server_probe(pack_root=pack_root)
            remote_saved = save_codex_app_server_config(
                {
                    "enabled": True,
                    "transport": "websocket_remote",
                    "base_url": "http://127.0.0.1:7331",
                    "websocket_url": "ws://127.0.0.1:7331/ws",
                    "tool_source_enabled": True,
                },
                pack_root=pack_root,
            )
            remote_status = codex_app_server_status(pack_root=pack_root)

    assert build_codex_app_server_command(config) == []
    assert saved["success"] is True
    assert saved["app_server"]["connection_status"] == "transport_url_mismatch"
    assert status["configured"] is False
    assert status["connection_status"] == "transport_url_mismatch"
    assert status["status_label"] == "Transport mismatch"
    assert status["transport_url_mismatch"] is True
    assert "loopback" in status["blocked_reason"]
    assert status["auth_required"] is True
    assert status["auth_configured"] is True
    assert status["command"] == []
    assert status["tool_source"]["status"] == "transport_url_mismatch"
    assert status["automation_endpoint"]["status"] == "transport_url_mismatch"
    assert probe["probe"]["status"] == "transport_url_mismatch"
    assert app_secret not in _text(saved)
    assert app_secret not in _text(status)
    assert app_secret not in _text(probe)
    assert remote_saved["app_server"]["connection_status"] == "transport_url_mismatch"
    assert remote_status["configured"] is False
    assert remote_status["connection_status"] == "transport_url_mismatch"
    assert "non-loopback" in remote_status["blocked_reason"]


def test_codex_app_server_rejects_query_secret_urls_without_echoing_secret():
    from domain.codex.app_server import (
        build_codex_app_server_command,
        codex_app_server_probe,
        codex_app_server_status,
        save_codex_app_server_config,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        pack_root = Path(tmpdir)
        secrets_dir = pack_root / "user_data" / "secrets"
        raw_secret = _fresh_token()
        env = {
            "RUMI_DEFAULTSPACK_SECRETS_DIR": str(secrets_dir),
            "RUMI_CODEX_APP_SERVER_WS_TOKEN": _fresh_token(),
            "RUMI_CODEX_APP_SERVER_SHARED_SECRET": "",
        }
        config = {
            "enabled": True,
            "transport": "websocket_loopback",
            "base_url": f"http://127.0.0.1:7331?access_token={raw_secret}",
            "websocket_url": f"ws://127.0.0.1:7331/ws?token={raw_secret}",
            "tool_source_enabled": True,
            "automation_endpoint_enabled": True,
        }
        with patch.dict(os.environ, env, clear=False):
            saved = save_codex_app_server_config(config, pack_root=pack_root)
            status = codex_app_server_status(pack_root=pack_root)
            probe = codex_app_server_probe(pack_root=pack_root)

    assert build_codex_app_server_command(config) == []
    assert saved["success"] is True
    assert saved["app_server"]["connection_status"] == "url_secret_rejected"
    assert status["configured"] is False
    assert status["connection_status"] == "url_secret_rejected"
    assert status["status_label"] == "URL secret rejected"
    assert status["url_secret_rejected"] is True
    assert status["base_url"] == ""
    assert status["websocket_url"] == ""
    assert status["command"] == []
    assert status["tool_source"]["status"] == "url_secret_rejected"
    assert status["automation_endpoint"]["status"] == "url_secret_rejected"
    assert probe["probe"]["status"] == "url_secret_rejected"
    assert raw_secret not in _text(saved)
    assert raw_secret not in _text(status)
    assert raw_secret not in _text(probe)


def test_codex_app_server_probe_never_uses_codex_access_token_for_app_server_auth():
    from domain.codex.app_server import codex_app_server_probe, save_codex_app_server_config
    from domain.codex.connection_store import save_codex_access_token

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    with tempfile.TemporaryDirectory() as tmpdir:
        pack_root = Path(tmpdir)
        secrets_dir = pack_root / "user_data" / "secrets"
        codex_token = _fresh_token()
        app_secret = _fresh_token()
        captured_headers: dict[str, str] = {}
        env = {
            "RUMI_DEFAULTSPACK_SECRETS_DIR": str(secrets_dir),
            "RUMI_CODEX_ACCESS_TOKEN": "",
            "CODEX_ACCESS_TOKEN": "",
            "RUMI_CODEX_APP_SERVER_WS_TOKEN": "",
            "RUMI_CODEX_APP_SERVER_SHARED_SECRET": "",
        }

        def fake_urlopen(request, timeout):
            del timeout
            captured_headers.update(dict(request.header_items()))
            return FakeResponse()

        with patch.dict(os.environ, env, clear=False):
            save_codex_access_token(codex_token, pack_root=pack_root)
            save_codex_app_server_config(
                {
                    "enabled": True,
                    "transport": "websocket_remote",
                    "base_url": "https://codex-app.example.test",
                    "websocket_url": "wss://codex-app.example.test/ws",
                },
                pack_root=pack_root,
            )
            blocked = codex_app_server_probe(pack_root=pack_root)

        with patch.dict(os.environ, {**env, "RUMI_CODEX_APP_SERVER_WS_TOKEN": app_secret}, clear=False):
            with patch("urllib.request.urlopen", fake_urlopen):
                probed = codex_app_server_probe(pack_root=pack_root)

    assert blocked["probe"]["status"] == "blocked_auth_required"
    assert probed["probe"]["status"] == "ok"
    assert captured_headers["Authorization"] == f"Bearer {app_secret}"
    assert codex_token not in _text(captured_headers)
    assert app_secret not in _text(probed)


def test_codex_app_server_transport_command_uses_file_paths_not_raw_tokens(tmp_path):
    from domain.codex.app_server import build_codex_app_server_command, codex_app_server_status, save_codex_app_server_config

    app_secret = _fresh_token()
    token_file = tmp_path / "codex-app-server.token"
    token_file.write_text(app_secret, encoding="utf-8")

    assert build_codex_app_server_command({}) == []

    command = build_codex_app_server_command(
        {
            "enabled": True,
            "transport": "unix",
            "unix_socket_path": "/tmp/rumi-codex.sock",
            "ws_token_file": str(token_file),
            "ws_token": app_secret,
        }
    )

    assert command == [
        "codex",
        "app-server",
        "unix",
        "--socket",
        "/tmp/rumi-codex.sock",
        "--ws-token-file",
        str(token_file),
    ]
    assert app_secret not in _text(command)

    with tempfile.TemporaryDirectory() as tmpdir:
        pack_root = Path(tmpdir)
        saved = save_codex_app_server_config(
            {
                "enabled": True,
                "transport": "stdio",
                "tool_source_enabled": True,
            },
            pack_root=pack_root,
        )
        status = codex_app_server_status(pack_root=pack_root)

    assert saved["success"] is True
    assert status["transport"] == "stdio"
    assert status["connection_status"] == "configured"
    assert status["command"] == ["codex", "app-server", "stdio"]


def test_frontend_registry_drops_client_supplied_codex_secret_payloads():
    from domain.frontend.registry import FrontendRegistry

    with tempfile.TemporaryDirectory() as tmpdir:
        pack_root = Path(tmpdir)
        token = _fresh_token()
        env = {
            "RUMI_DEFAULTSPACK_SECRETS_DIR": str(pack_root / "user_data" / "secrets"),
            "RUMI_CODEX_ACCESS_TOKEN": "",
            "CODEX_ACCESS_TOKEN": "",
        }
        with patch.dict(os.environ, env, clear=False):
            values = FrontendRegistry(pack_root=pack_root).update_settings(
                {
                    "accounts_connections": {
                        "providers": {
                            "codex": {
                                "access_token": token,
                                "token": token,
                                "configured": True,
                            },
                        },
                    },
                    "tools_mcp": {
                        "codex_app_server": {
                            "token": token,
                            "websocket_url": "wss://codex-app.example.test/ws",
                        },
                    },
                }
            )

    assert values["accounts_connections"]["providers"]["codex"]["configured"] is False
    assert values["tools_mcp"]["codex_app_server"]["connection_status"] == "not_configured"
    assert token not in _text(values)
