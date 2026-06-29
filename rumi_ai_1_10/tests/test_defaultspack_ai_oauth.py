from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


class TestDefaultspackAiOauth(unittest.TestCase):
    @staticmethod
    def _google_client_json() -> str:
        return """
        {
          "installed": {
            "client_id": "test-client.apps.googleusercontent.com",
            "client_secret": "test-secret",
            "redirect_uris": ["http://127.0.0.1"]
          }
        }
        """

    def test_google_oauth_status_tracks_client_and_connection(self):
        from domain.ai_client.oauth_store import (
            disconnect_provider_oauth,
            get_provider_access_token,
            provider_oauth_status,
            save_provider_oauth_client_config,
            save_provider_oauth_connection,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            pack_root = Path(tmpdir)
            secrets_dir = pack_root / "user_data" / "secrets"
            env = {"RUMI_DEFAULTSPACK_SECRETS_DIR": str(secrets_dir)}
            with patch.dict(os.environ, env, clear=True):
                saved_client = save_provider_oauth_client_config(
                    "google",
                    self._google_client_json(),
                    pack_root=pack_root,
                )
                status = provider_oauth_status("google", pack_root=pack_root)
                saved_connection = save_provider_oauth_connection(
                    "google",
                    {
                        "access_token": "oauth-access-token",
                        "refresh_token": "oauth-refresh-token",
                        "expires_in": 3600,
                        "scope": "openid email profile https://www.googleapis.com/auth/generative-language",
                        "token_type": "Bearer",
                    },
                    userinfo={"email": "user@example.test", "name": "OAuth User"},
                    pack_root=pack_root,
                )
                connected_status = provider_oauth_status("google", pack_root=pack_root)
                access_token = get_provider_access_token("google", pack_root=pack_root)
                disconnect_provider_oauth("google", pack_root=pack_root)
                disconnected_status = provider_oauth_status("google", pack_root=pack_root)

        self.assertTrue(saved_client["success"])
        self.assertTrue(status["client_configured"])
        self.assertFalse(status["connected"])
        self.assertTrue(saved_connection["success"])
        self.assertTrue(connected_status["connected"])
        self.assertEqual(connected_status["email"], "user@example.test")
        self.assertEqual(access_token, "oauth-access-token")
        self.assertFalse(disconnected_status["connected"])

    def test_google_oauth_start_builds_loopback_callback(self):
        from domain.ai_client.oauth_store import (
            save_provider_oauth_client_config,
            start_provider_oauth,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            pack_root = Path(tmpdir)
            secrets_dir = pack_root / "user_data" / "secrets"
            env = {"RUMI_DEFAULTSPACK_SECRETS_DIR": str(secrets_dir)}
            with patch.dict(os.environ, env, clear=True):
                save_provider_oauth_client_config("google", self._google_client_json(), pack_root=pack_root)
                started = start_provider_oauth(
                    "google",
                    request_headers={"Host": "127.0.0.1:8766"},
                    pack_root=pack_root,
                )

        self.assertTrue(started["success"])
        self.assertIn("accounts.google.com", started["authorize_url"])
        self.assertEqual(started["redirect_uri"], "http://127.0.0.1:8766/api/ai/oauth/google/callback")
        self.assertIn("state=", started["authorize_url"])

    def test_google_workspace_scope_mode_matches_drive_gmail_manifest_scopes(self):
        from domain.ai_client.oauth_store import (
            save_provider_oauth_client_config,
            start_provider_oauth,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            pack_root = Path(tmpdir)
            secrets_dir = pack_root / "user_data" / "secrets"
            env = {"RUMI_DEFAULTSPACK_SECRETS_DIR": str(secrets_dir)}
            with patch.dict(os.environ, env, clear=True):
                save_provider_oauth_client_config("google", self._google_client_json(), pack_root=pack_root)
                started = start_provider_oauth(
                    "google",
                    request_headers={"Host": "127.0.0.1:8766"},
                    scope_mode="google_workspace",
                    pack_root=pack_root,
                )

        self.assertTrue(started["success"], started)
        self.assertEqual(started["scope_mode"], "google_workspace")
        self.assertIn("https://www.googleapis.com/auth/drive.file", started["scopes"])
        self.assertIn("https://www.googleapis.com/auth/gmail.labels", started["scopes"])
        self.assertNotIn("https://www.googleapis.com/auth/generative-language", started["scopes"])
        self.assertIn(
            "scope=openid+email+profile+https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fdrive.file+https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fgmail.labels",
            started["authorize_url"],
        )

    def test_google_services_can_select_restricted_gmail_scope_mode(self):
        from domain.ai_client.oauth_store import (
            provider_oauth_status,
            save_provider_oauth_client_config,
            start_provider_oauth,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            pack_root = Path(tmpdir)
            secrets_dir = pack_root / "user_data" / "secrets"
            env = {"RUMI_DEFAULTSPACK_SECRETS_DIR": str(secrets_dir)}
            with patch.dict(os.environ, env, clear=True):
                save_provider_oauth_client_config("google", self._google_client_json(), pack_root=pack_root)
                started = start_provider_oauth(
                    "google",
                    request_headers={"Host": "127.0.0.1:8766"},
                    services=["identity", "gmail_metadata"],
                    pack_root=pack_root,
                )
                status = provider_oauth_status("google", pack_root=pack_root)

        self.assertTrue(started["success"], started)
        self.assertEqual(started["scope_mode"], "google_gmail_metadata")
        self.assertEqual(started["services"], ["identity", "gmail_metadata"])
        self.assertIn("https://www.googleapis.com/auth/gmail.metadata", started["scopes"])
        self.assertNotIn("https://www.googleapis.com/auth/gmail.readonly", started["scopes"])
        restricted_modes = {
            item["id"]: item
            for item in status["scope_modes"]
            if item.get("restricted")
        }
        self.assertIn("google_gmail_metadata", restricted_modes)
        self.assertIn("google_gmail_readonly", restricted_modes)
        self.assertIn("Restricted Gmail scopes", restricted_modes["google_gmail_metadata"]["warning"])

    def test_cloudflare_oauth_is_not_connectable_until_scopes_are_configured(self):
        from domain.ai_client.oauth_store import provider_oauth_status, start_provider_oauth

        with tempfile.TemporaryDirectory() as tmpdir:
            pack_root = Path(tmpdir)
            status = provider_oauth_status("cloudflare", pack_root=pack_root)
            started = start_provider_oauth(
                "cloudflare",
                request_headers={"Host": "127.0.0.1:8766"},
                pack_root=pack_root,
            )

        self.assertFalse(status["supported"])
        self.assertFalse(status["backend_supported"])
        self.assertFalse(status["connect_enabled"])
        self.assertEqual(status["connection_status"], "missing_scope_config")
        self.assertEqual(status["disabled_reason"], "Configure self-host OAuth")
        self.assertFalse(started["success"])
        self.assertEqual(started["status"], "missing_scope_config")

    def test_finish_provider_oauth_exchanges_code_and_persists_connection(self):
        from domain.ai_client.oauth_store import (
            finish_provider_oauth,
            provider_oauth_status,
            save_provider_oauth_client_config,
            start_provider_oauth,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            pack_root = Path(tmpdir)
            secrets_dir = pack_root / "user_data" / "secrets"
            env = {"RUMI_DEFAULTSPACK_SECRETS_DIR": str(secrets_dir)}
            with patch.dict(os.environ, env, clear=True):
                save_provider_oauth_client_config("google", self._google_client_json(), pack_root=pack_root)
                started = start_provider_oauth(
                    "google",
                    request_headers={"Host": "127.0.0.1:8766"},
                    pack_root=pack_root,
                )
                with patch(
                    "domain.ai_client.oauth_store._exchange_code_for_tokens",
                    return_value={
                        "access_token": "oauth-access-token",
                        "refresh_token": "oauth-refresh-token",
                        "expires_in": 3600,
                        "scope": "openid email profile https://www.googleapis.com/auth/generative-language",
                        "token_type": "Bearer",
                    },
                ), patch(
                    "domain.ai_client.oauth_store._fetch_userinfo",
                    return_value={"email": "user@example.test", "name": "OAuth User"},
                ):
                    result = finish_provider_oauth(
                        "google",
                        {"code": "oauth-code", "state": started["state"]},
                        pack_root=pack_root,
                    )
                status = provider_oauth_status("google", pack_root=pack_root)

        self.assertTrue(result["success"])
        self.assertTrue(status["connected"])
        self.assertEqual(status["display_name"], "OAuth User")

    def test_oauth_block_callback_returns_static_postmessage_page(self):
        from blocks.ai import oauth as oauth_block

        with patch.object(
            oauth_block,
            "finish_provider_oauth",
            return_value={
                "success": True,
                "provider_id": "google",
                "email": "user@example.test",
                "display_name": "OAuth User",
            },
        ):
            result = oauth_block.run(
                {
                    "_method": "GET",
                    "provider_id": "google",
                    "code": "oauth-code",
                    "state": "oauth-state",
                },
                {},
            )

        self.assertTrue(result["_static"])
        self.assertIn("window.opener.postMessage", str(result["body"]))
        self.assertIn("Browser login connected", str(result["body"]))


if __name__ == "__main__":
    unittest.main()
