"""
test_wave25_fix_token_log.py - W25-FIX: Token log prefix display tests

Tests:
1. HMAC token log contains 8-char prefix
2. get_active_key() return value stored in internal_token
3. Full token not leaked in INFO-level log
4. Explicit token skips HMAC prefix log
5. Retrieval instructions (hmac_keys.json) in log
6. Short token (< 8 chars) does not crash
7. Empty token does not crash
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from core_runtime.pack_api_server import PackAPIServer


FAKE_TOKEN = "ABCDEFGHijklmnopqrstuvwxyz0123456789ABCDEF"  # 43 chars, like token_urlsafe(32)


class TestTokenLogPrefix:
    """W25-FIX: Token log output tests."""

    @patch("core_runtime.pack_api_server.get_hmac_key_manager")
    def test_hmac_token_log_contains_prefix(self, mock_get_hmac, caplog):
        """Log must contain the first 8 characters of the token as prefix."""
        mock_mgr = MagicMock()
        mock_mgr.get_active_key.return_value = FAKE_TOKEN
        mock_get_hmac.return_value = mock_mgr

        with caplog.at_level(logging.DEBUG, logger="core_runtime.pack_api_server"):
            PackAPIServer()

        info_messages = [r.message for r in caplog.records if r.levelno == logging.INFO]
        expected_prefix = FAKE_TOKEN[:8] + "..."
        assert any(expected_prefix in msg for msg in info_messages), (
            f"Expected prefix {expected_prefix!r} in INFO logs; got {info_messages}"
        )

    @patch("core_runtime.pack_api_server.get_hmac_key_manager")
    def test_hmac_token_stored_correctly(self, mock_get_hmac):
        """get_active_key() return value must be stored in server.internal_token."""
        mock_mgr = MagicMock()
        mock_mgr.get_active_key.return_value = FAKE_TOKEN
        mock_get_hmac.return_value = mock_mgr

        server = PackAPIServer()
        assert server.internal_token == FAKE_TOKEN

    @patch("core_runtime.pack_api_server.get_hmac_key_manager")
    def test_full_token_not_in_info_log(self, mock_get_hmac, caplog):
        """Full token value must NOT appear in INFO-level log records."""
        mock_mgr = MagicMock()
        mock_mgr.get_active_key.return_value = FAKE_TOKEN
        mock_get_hmac.return_value = mock_mgr

        with caplog.at_level(logging.DEBUG, logger="core_runtime.pack_api_server"):
            PackAPIServer()

        info_messages = [r.message for r in caplog.records if r.levelno == logging.INFO]
        for msg in info_messages:
            assert FAKE_TOKEN not in msg, (
                f"Full token leaked in INFO log: {msg!r}"
            )

    @patch("core_runtime.pack_api_server.get_hmac_key_manager")
    def test_explicit_token_no_hmac_log(self, mock_get_hmac, caplog):
        """When internal_token is explicitly provided, no HMAC prefix log should appear."""
        mock_mgr = MagicMock()
        mock_get_hmac.return_value = mock_mgr

        with caplog.at_level(logging.DEBUG, logger="core_runtime.pack_api_server"):
            PackAPIServer(internal_token="explicit-user-token")

        all_messages = " ".join(r.message for r in caplog.records)
        assert "HMAC-managed API token (prefix)" not in all_messages, (
            "HMAC prefix log should not appear when token is explicitly set"
        )
        mock_mgr.get_active_key.assert_not_called()

    @patch("core_runtime.pack_api_server.get_hmac_key_manager")
    def test_retrieval_instructions_in_log(self, mock_get_hmac, caplog):
        """Log must contain instructions for retrieving the full token."""
        mock_mgr = MagicMock()
        mock_mgr.get_active_key.return_value = FAKE_TOKEN
        mock_get_hmac.return_value = mock_mgr

        with caplog.at_level(logging.DEBUG, logger="core_runtime.pack_api_server"):
            PackAPIServer()

        warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("hmac_keys.json" in msg for msg in warning_messages), (
            f"Expected hmac_keys.json reference in WARNING logs; got {warning_messages}"
        )

    @patch("core_runtime.pack_api_server.get_hmac_key_manager")
    def test_short_token_no_crash(self, mock_get_hmac, caplog):
        """Token shorter than 8 chars must not cause an error."""
        mock_mgr = MagicMock()
        mock_mgr.get_active_key.return_value = "short"
        mock_get_hmac.return_value = mock_mgr

        with caplog.at_level(logging.DEBUG, logger="core_runtime.pack_api_server"):
            server = PackAPIServer()

        assert server.internal_token == "short"
        info_messages = [r.message for r in caplog.records if r.levelno == logging.INFO]
        # Short token is printed as-is (no "..." suffix since < 8 chars)
        assert any("short" in msg for msg in info_messages)

    @patch("core_runtime.pack_api_server.get_hmac_key_manager")
    def test_empty_token_no_crash(self, mock_get_hmac, caplog):
        """Empty string from get_active_key() must not crash."""
        mock_mgr = MagicMock()
        mock_mgr.get_active_key.return_value = ""
        mock_get_hmac.return_value = mock_mgr

        with caplog.at_level(logging.DEBUG, logger="core_runtime.pack_api_server"):
            server = PackAPIServer()

        assert server.internal_token == ""
        info_messages = [r.message for r in caplog.records if r.levelno == logging.INFO]
        assert any("(empty)" in msg for msg in info_messages), (
            f"Expected (empty) marker in INFO logs for empty token; got {info_messages}"
        )
