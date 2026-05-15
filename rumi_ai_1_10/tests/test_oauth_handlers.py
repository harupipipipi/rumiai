"""OAuthHandlersMixin の基本テスト"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.parse import urlparse, parse_qs

# テスト対象のインポートパスを解決
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from core_runtime.api.oauth_handlers import (  # noqa: E402
    OAuthHandlersMixin,
    _FERNET_AVAILABLE,
    _Fernet,
    _generate_code_verifier,
    _generate_code_challenge,
    _save_tokens,
    _pkce_store,
    _CLIENT_ID,
    _REDIRECT_URI,
    _SCOPE,
)

_OAUTH_MODULE = sys.modules[OAuthHandlersMixin.__module__]
_LOAD_TOKENS = _save_tokens.__globals__["_load_tokens"]


class TestPKCEGeneration(unittest.TestCase):
    """PKCE code_verifier / code_challenge のテスト"""

    def test_code_verifier_length(self):
        verifier = _generate_code_verifier()
        # RFC 7636: 43〜128文字
        self.assertGreaterEqual(len(verifier), 43)
        self.assertLessEqual(len(verifier), 128)

    def test_code_verifier_characters(self):
        """code_verifier は URL-safe base64 文字のみで構成される"""
        verifier = _generate_code_verifier()
        self.assertRegex(verifier, r'^[A-Za-z0-9_\-]+$')

    def test_code_verifier_uniqueness(self):
        """2回呼ぶと異なる値になる"""
        v1 = _generate_code_verifier()
        v2 = _generate_code_verifier()
        self.assertNotEqual(v1, v2)

    def test_code_challenge_is_s256(self):
        """code_challenge が SHA-256 + base64url(no padding) であること"""
        verifier = "test_verifier_string_1234567890abcdefghijk"
        challenge = _generate_code_challenge(verifier)

        # 手動計算で検証
        expected_digest = hashlib.sha256(verifier.encode("ascii")).digest()
        expected_challenge = base64.urlsafe_b64encode(expected_digest).rstrip(b"=").decode("ascii")

        self.assertEqual(challenge, expected_challenge)

    def test_code_challenge_no_padding(self):
        """code_challenge に = パディングが含まれないこと"""
        verifier = _generate_code_verifier()
        challenge = _generate_code_challenge(verifier)
        self.assertNotIn("=", challenge)


class _FakeHandler(OAuthHandlersMixin):
    """テスト用フェイクハンドラ"""
    kernel = None


class TestOAuthStart(unittest.TestCase):
    """GET /api/setup/oauth/start のレスポンス形式テスト"""

    def setUp(self):
        _pkce_store.clear()

    def test_start_returns_authorize_url_and_state(self):
        handler = _FakeHandler()
        result = handler._oauth_start()
        self.assertIn("authorize_url", result)
        self.assertIn("state", result)
        self.assertIsInstance(result["authorize_url"], str)
        self.assertIsInstance(result["state"], str)

    def test_authorize_url_contains_required_params(self):
        handler = _FakeHandler()
        result = handler._oauth_start()
        url = result["authorize_url"]
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        self.assertIn("client_id", params)
        self.assertEqual(params["client_id"][0], _CLIENT_ID)
        self.assertIn("redirect_uri", params)
        self.assertEqual(params["redirect_uri"][0], _REDIRECT_URI)
        self.assertIn("response_type", params)
        self.assertEqual(params["response_type"][0], "code")
        self.assertIn("code_challenge_method", params)
        self.assertEqual(params["code_challenge_method"][0], "S256")
        self.assertIn("code_challenge", params)
        self.assertIn("scope", params)
        self.assertEqual(params["scope"][0], _SCOPE)
        self.assertIn("state", params)

    def test_state_stored_in_pkce_store(self):
        handler = _FakeHandler()
        result = handler._oauth_start()
        state = result["state"]
        self.assertIn(state, _pkce_store)
        self.assertIn("code_verifier", _pkce_store[state])
        self.assertIn("created_at", _pkce_store[state])

    def test_code_challenge_matches_stored_verifier(self):
        """認可 URL の code_challenge が保存された verifier から導出できること"""
        handler = _FakeHandler()
        result = handler._oauth_start()
        state = result["state"]
        verifier = _pkce_store[state]["code_verifier"]

        url = result["authorize_url"]
        params = parse_qs(urlparse(url).query)
        challenge_in_url = params["code_challenge"][0]

        expected = _generate_code_challenge(verifier)
        self.assertEqual(challenge_in_url, expected)


class TestOAuthCallback(unittest.TestCase):
    """GET /callback のバリデーションテスト"""

    def setUp(self):
        _pkce_store.clear()

    def test_callback_missing_code(self):
        handler = _FakeHandler()
        result = handler._oauth_callback({"state": ["test_state"]})
        self.assertIsNotNone(result)
        self.assertIn("error", result)

    def test_callback_missing_state(self):
        handler = _FakeHandler()
        result = handler._oauth_callback({"code": ["test_code"]})
        self.assertIsNotNone(result)
        self.assertIn("error", result)

    def test_callback_invalid_state(self):
        handler = _FakeHandler()
        result = handler._oauth_callback({
            "code": ["test_code"],
            "state": ["invalid_state"],
        })
        self.assertIsNotNone(result)
        self.assertIn("error", result)
        self.assertIn("Invalid or expired state", result["error"])

    def test_callback_oauth_error(self):
        handler = _FakeHandler()
        result = handler._oauth_callback({
            "error": ["access_denied"],
            "error_description": ["User denied access"],
        })
        self.assertIsNotNone(result)
        self.assertIn("error", result)
        self.assertIn("OAuth error", result["error"])

    def test_callback_expired_state(self):
        """5分超過した PKCE エントリは拒否される"""
        import time
        state = "expired_state"
        _pkce_store[state] = {
            "code_verifier": "test_verifier",
            "created_at": time.time() - 600,  # 10分前
        }
        handler = _FakeHandler()
        result = handler._oauth_callback({
            "code": ["test_code"],
            "state": [state],
        })
        self.assertIsNotNone(result)
        self.assertIn("error", result)
        self.assertIn("expired", result["error"])

    def test_callback_continues_when_cryptography_is_unavailable(self):
        state = "available_state"
        _pkce_store[state] = {
            "code_verifier": "test_verifier",
            "created_at": time.time(),
        }

        with patch.object(_OAUTH_MODULE, "_log_internal_error") as mock_log_internal_error, patch.object(
            _OAUTH_MODULE,
            "_http_get_json",
            return_value=None,
        ), patch.object(
            _OAUTH_MODULE,
            "_http_post_form",
            return_value={
                "access_token": "token-access",
                "refresh_token": "token-refresh",
                "token_type": "bearer",
            },
        ), patch.object(
            _OAUTH_MODULE,
            "_FERNET_AVAILABLE",
            False,
        ), patch.object(
            _OAUTH_MODULE,
            "_Fernet",
            None,
        ):
            handler = _FakeHandler()
            result = handler._oauth_callback({
                "code": ["test_code"],
                "state": [state],
            })

        self.assertIsNone(result)
        mock_log_internal_error.assert_called_once()


class TestOAuthTokenStorage(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.token_path = Path(self._tmpdir.name) / "oauth_tokens.json"
        self.path_patch = patch.dict(
            _save_tokens.__globals__,
            {"_get_token_path": lambda: self.token_path},
        )
        self.path_patch.start()

    def tearDown(self):
        self.path_patch.stop()
        self._tmpdir.cleanup()

    @unittest.skipUnless(_FERNET_AVAILABLE and _Fernet is not None, "cryptography unavailable")
    def test_tokens_are_saved_encrypted(self):
        _save_tokens({"access_token": "access", "refresh_token": "refresh"})
        raw_text = self.token_path.read_text(encoding="utf-8")
        raw = json.loads(raw_text)

        self.assertEqual(raw.get("version"), "1.0")
        self.assertEqual(raw.get("encryption"), "fernet")
        self.assertIn("payload", raw)
        self.assertNotIn("access_token", raw_text)
        self.assertNotIn("refresh_token", raw_text)
        self.assertNotIn("access", raw_text)
        self.assertNotIn("refresh", raw_text)
        self.assertTrue(self.token_path.with_name(".oauth_tokens.key").is_file())

    @unittest.skipUnless(_FERNET_AVAILABLE and _Fernet is not None, "cryptography unavailable")
    def test_load_tokens_decrypts_encrypted_payload(self):
        expected = {"access_token": "access", "refresh_token": "refresh"}
        _save_tokens(expected)
        self.assertEqual(_LOAD_TOKENS(), expected)

    def test_load_tokens_keeps_legacy_plaintext_compatibility(self):
        legacy = {"access_token": "legacy", "refresh_token": "legacy-refresh"}
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_path.write_text(json.dumps(legacy), encoding="utf-8")
        self.assertEqual(_LOAD_TOKENS(), legacy)

    @unittest.skipUnless(_FERNET_AVAILABLE and _Fernet is not None, "cryptography unavailable")
    def test_legacy_plaintext_migrates_to_encrypted_on_next_save(self):
        legacy = {"access_token": "legacy", "refresh_token": "legacy-refresh"}
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_path.write_text(json.dumps(legacy), encoding="utf-8")

        self.assertEqual(_LOAD_TOKENS(), legacy)
        _save_tokens(legacy)
        raw_text = self.token_path.read_text(encoding="utf-8")
        raw = json.loads(raw_text)

        self.assertEqual(raw.get("version"), "1.0")
        self.assertEqual(raw.get("encryption"), "fernet")
        self.assertIn("payload", raw)
        self.assertNotIn("legacy", raw_text)
        self.assertEqual(_LOAD_TOKENS(), legacy)

    @unittest.skipUnless(_FERNET_AVAILABLE and _Fernet is not None, "cryptography unavailable")
    def test_empty_key_file_is_replaced_safely(self):
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        key_path = self.token_path.with_name(".oauth_tokens.key")
        key_path.write_bytes(b"")

        _save_tokens({"access_token": "access"})

        self.assertGreater(key_path.stat().st_size, 0)
        self.assertEqual(_LOAD_TOKENS(), {"access_token": "access"})

    @unittest.skipUnless(_FERNET_AVAILABLE and _Fernet is not None, "cryptography unavailable")
    def test_corrupt_key_file_is_replaced_safely_for_new_save(self):
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        key_path = self.token_path.with_name(".oauth_tokens.key")
        key_path.write_bytes(b"not-a-fernet-key")

        _save_tokens({"access_token": "access"})

        self.assertNotEqual(key_path.read_bytes(), b"not-a-fernet-key")
        self.assertEqual(_LOAD_TOKENS(), {"access_token": "access"})


class TestOAuthSendRedirect(unittest.TestCase):
    """_oauth_send_redirect のテスト"""

    def test_redirect_sends_302(self):
        handler = _FakeHandler()
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()

        handler._oauth_send_redirect("/setup?linked=true")

        handler.send_response.assert_called_once_with(302)
        handler.send_header.assert_called_once_with("Location", "/setup?linked=true")
        handler.end_headers.assert_called_once()


class TestOAuthResultPage(unittest.TestCase):
    """_oauth_send_result_page のテスト"""

    def test_result_page_sends_html(self):
        handler = _FakeHandler()
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()
        handler.wfile = io.BytesIO()

        handler._oauth_send_result_page(
            "Connected",
            "Return to the app.",
            success=True,
        )

        handler.send_response.assert_called_once_with(200)
        handler.send_header.assert_any_call("Content-Type", "text/html; charset=utf-8")
        body = handler.wfile.getvalue().decode("utf-8")
        self.assertIn("Connected", body)
        self.assertIn("Return to the app.", body)
        self.assertIn("Close this tab", body)


if __name__ == "__main__":
    unittest.main()
