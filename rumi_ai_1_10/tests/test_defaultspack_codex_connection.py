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


def test_codex_app_server_rejects_non_loopback_websocket_without_token():
    from domain.codex.app_server import codex_app_server_status, save_codex_app_server_config
    from domain.codex.connection_store import save_codex_access_token

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
            rejected = save_codex_app_server_config(
                {
                    "enabled": True,
                    "base_url": "https://codex-app.example.test",
                    "websocket_url": "wss://codex-app.example.test/ws",
                    "tool_source_enabled": True,
                    "automation_endpoint_enabled": True,
                },
                pack_root=pack_root,
            )
            save_codex_access_token(token, pack_root=pack_root)
            accepted = save_codex_app_server_config(
                {
                    "enabled": True,
                    "base_url": "https://codex-app.example.test",
                    "websocket_url": "wss://codex-app.example.test/ws",
                    "tool_source_enabled": True,
                    "automation_endpoint_enabled": True,
                },
                pack_root=pack_root,
            )
            status = codex_app_server_status(pack_root=pack_root)

    assert rejected["success"] is False
    assert rejected["code"] == "AUTH_REQUIRED_FOR_NON_LOOPBACK_WEBSOCKET"
    assert accepted["success"] is True
    assert status["auth_required"] is True
    assert status["auth_configured"] is True
    assert token not in _text(accepted)
    assert token not in _text(status)


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
