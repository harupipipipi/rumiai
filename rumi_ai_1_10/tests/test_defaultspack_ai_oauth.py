from __future__ import annotations

import os
import sys
import tempfile
import unittest
import urllib.parse
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

    def test_cloudflare_oauth_waits_for_self_host_scopes(self):
        from domain.ai_client.oauth_store import provider_oauth_status, start_provider_oauth

        with tempfile.TemporaryDirectory() as tmpdir:
            pack_root = Path(tmpdir)
            status = provider_oauth_status("cloudflare", pack_root=pack_root)
            started = start_provider_oauth(
                "cloudflare",
                request_headers={"Host": "127.0.0.1:8766"},
                pack_root=pack_root,
            )

        self.assertTrue(status["supported"])
        self.assertTrue(status["backend_supported"])
        self.assertFalse(status["connect_enabled"])
        self.assertEqual(status["connection_status"], "missing_scope_config")
        self.assertEqual(status["disabled_reason"], "Configure self-host OAuth")
        self.assertFalse(started["success"])
        self.assertEqual(started["error"], "oauth client config is not saved")

    def test_cloudflare_oauth_start_uses_env_client_and_manifest_endpoint(self):
        from domain.ai_client.oauth_store import provider_oauth_status, start_provider_oauth

        with tempfile.TemporaryDirectory() as tmpdir:
            pack_root = Path(tmpdir)
            (pack_root / ".env").write_text(
                "\n".join(
                    [
                        "RUMI_CLOUDFLARE_OAUTH_CLIENT_ID=cloudflare-client-id",
                        "RUMI_CLOUDFLARE_OAUTH_CLIENT_SECRET=cloudflare-client-secret",
                        "RUMI_CLOUDFLARE_OAUTH_SCOPES=account:read user:read",
                        "RUMI_CLOUDFLARE_OAUTH_REDIRECT_URI=http://127.0.0.1:8766/api/ai/oauth/cloudflare/callback",
                    ]
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                status = provider_oauth_status("cloudflare", pack_root=pack_root)
                started = start_provider_oauth(
                    "cloudflare",
                    request_headers={"Host": "127.0.0.1:8766"},
                    pack_root=pack_root,
                )

        self.assertTrue(status["supported"])
        self.assertTrue(status["backend_supported"])
        self.assertTrue(status["client_configured"])
        self.assertEqual(status["client_source"], "env")
        self.assertFalse(status["client_can_clear"])
        self.assertTrue(status["connect_enabled"])
        self.assertEqual(status["connection_status"], "not_connected")
        self.assertTrue(started["success"], started)
        parsed = urllib.parse.urlparse(started["authorize_url"])
        params = urllib.parse.parse_qs(parsed.query)
        self.assertEqual(f"{parsed.scheme}://{parsed.netloc}{parsed.path}", "https://dash.cloudflare.com/oauth2/auth")
        self.assertEqual(params["client_id"], ["cloudflare-client-id"])
        self.assertEqual(params["scope"], ["account:read user:read"])
        self.assertEqual(params["redirect_uri"], ["http://127.0.0.1:8766/api/ai/oauth/cloudflare/callback"])
        self.assertIn("code_challenge", params)
        self.assertNotIn("include_granted_scopes", params)
        self.assertNotIn("access_type", params)

    def test_cloudflare_env_access_token_counts_as_connected(self):
        from domain.ai_client.oauth_store import get_provider_access_token, provider_oauth_status

        with tempfile.TemporaryDirectory() as tmpdir:
            pack_root = Path(tmpdir)
            (pack_root / ".env").write_text(
                "RUMI_CLOUDFLARE_OAUTH_ACCESS_TOKEN=cloudflare-oauth-access\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                status = provider_oauth_status("cloudflare", pack_root=pack_root)
                access_token = get_provider_access_token("cloudflare", pack_root=pack_root)

        self.assertTrue(status["supported"])
        self.assertTrue(status["connected"])
        self.assertEqual(status["connection_status"], "connected")
        self.assertEqual(access_token, "cloudflare-oauth-access")

    def test_cloudflare_oauth_finish_uses_cloudflare_token_and_userinfo_endpoints(self):
        from domain.ai_client.oauth_store import finish_provider_oauth, start_provider_oauth

        captured: dict[str, str] = {}

        def fake_post(url: str, data: dict[str, str], *, timeout: float = 30.0) -> dict[str, object]:
            del timeout
            captured["post_url"] = url
            captured["client_secret"] = data.get("client_secret", "")
            return {
                "access_token": "cloudflare-access-token",
                "refresh_token": "cloudflare-refresh-token",
                "expires_in": 3600,
                "token_type": "Bearer",
            }

        def fake_get(url: str, access_token: str, *, timeout: float = 30.0) -> dict[str, object]:
            del timeout
            captured["get_url"] = url
            captured["access_token"] = access_token
            return {"email": "cloudflare-user@example.test", "name": "Cloudflare User"}

        with tempfile.TemporaryDirectory() as tmpdir:
            pack_root = Path(tmpdir)
            secrets_dir = pack_root / "user_data" / "secrets"
            (pack_root / ".env").write_text(
                "\n".join(
                    [
                        "RUMI_CLOUDFLARE_OAUTH_CLIENT_ID=cloudflare-client-id",
                        "RUMI_CLOUDFLARE_OAUTH_CLIENT_SECRET=cloudflare-client-secret",
                        "RUMI_CLOUDFLARE_OAUTH_SCOPES=account:read",
                    ]
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"RUMI_DEFAULTSPACK_SECRETS_DIR": str(secrets_dir)}, clear=True):
                started = start_provider_oauth(
                    "cloudflare",
                    request_headers={"Host": "127.0.0.1:8766"},
                    pack_root=pack_root,
                )
                with patch("domain.ai_client.oauth_store._http_post_form", side_effect=fake_post), patch(
                    "domain.ai_client.oauth_store._http_get_json",
                    side_effect=fake_get,
                ):
                    result = finish_provider_oauth(
                        "cloudflare",
                        {"code": "oauth-code", "state": started["state"]},
                        pack_root=pack_root,
                    )

        self.assertTrue(result["success"], result)
        self.assertEqual(captured["post_url"], "https://dash.cloudflare.com/oauth2/token")
        self.assertEqual(captured["get_url"], "https://dash.cloudflare.com/oauth2/userinfo")
        self.assertEqual(captured["client_secret"], "cloudflare-client-secret")
        self.assertEqual(captured["access_token"], "cloudflare-access-token")

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
