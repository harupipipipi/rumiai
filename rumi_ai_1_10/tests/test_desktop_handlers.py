"""
test_desktop_handlers.py - Tests for POST /api/desktop/token API handler.

Phase V-4: desktop_app:execute capability API tests.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock

# Ensure rumi_ai_1_10/ is on sys.path so 'core_runtime' is importable
_THIS_DIR = Path(__file__).resolve().parent          # tests/
_REPO_DIR = _THIS_DIR.parent                         # rumi_ai_1_10/
if str(_REPO_DIR) not in sys.path:
    sys.path.insert(0, str(_REPO_DIR))

from core_runtime.api.desktop_handlers import DesktopHandlersMixin


# ======================================================================
# Stub host class that provides _validate_pack_id
# ======================================================================

class _StubHost(DesktopHandlersMixin):
    """Minimal host providing _validate_pack_id for mixin tests."""

    def __init__(self, valid_pack_ids: Optional[list] = None):
        self._valid_ids = valid_pack_ids or ["test_pack"]

    def _validate_pack_id(self, pack_id: str) -> bool:
        return pack_id in self._valid_ids


# ======================================================================
# Mock helpers
# ======================================================================

class _GrantResult:
    """Minimal Grant check result."""
    def __init__(self, allowed: bool, config: Optional[dict] = None):
        self.allowed = allowed
        self.config = config


class _MockHandler:
    """Mock desktop capability handler."""
    def handle_execute(self, principal_id, args, grant_config):
        return {
            "token": "test-token-abc123",
            "port": 8765,
            "expires_in": 3600,
        }


class _MockHandlerError:
    """Mock desktop capability handler that returns error."""
    def handle_execute(self, principal_id, args, grant_config):
        return {"error": "Desktop app not configured"}


# ======================================================================
# Tests
# ======================================================================

class TestDesktopHandlers(unittest.TestCase):
    """Tests for DesktopHandlersMixin._desktop_issue_token."""

    def test_missing_pack_id(self):
        """pack_id が未指定の場合 → 400。"""
        host = _StubHost()
        result = host._desktop_issue_token({})
        self.assertEqual(result["status_code"], 400)
        self.assertIn("Missing", result["error"])

    def test_empty_pack_id(self):
        """pack_id が空文字の場合 → 400。"""
        host = _StubHost()
        result = host._desktop_issue_token({"pack_id": "  "})
        self.assertEqual(result["status_code"], 400)

    def test_invalid_pack_id(self):
        """不正な pack_id → 400。"""
        host = _StubHost(valid_pack_ids=["good_pack"])
        result = host._desktop_issue_token({"pack_id": "bad_pack"})
        self.assertEqual(result["status_code"], 400)
        self.assertIn("Invalid", result["error"])

    def test_no_grant_returns_403(self):
        """Grant がない場合 → 403。"""
        host = _StubHost(valid_pack_ids=["test_pack"])

        mock_grant_manager = MagicMock()
        mock_grant_manager.check.return_value = _GrantResult(allowed=False)

        import core_runtime.capability_grant_manager as cgm_mod
        orig_grant = getattr(cgm_mod, "get_capability_grant_manager", None)
        cgm_mod.get_capability_grant_manager = lambda: mock_grant_manager
        try:
            result = host._desktop_issue_token({"pack_id": "test_pack"})
            self.assertEqual(result["status_code"], 403)
            self.assertIn("not granted", result["error"])
        finally:
            if orig_grant:
                cgm_mod.get_capability_grant_manager = orig_grant

    def test_handler_not_available(self):
        """handler が DI に登録されていない場合 → 503。"""
        host = _StubHost(valid_pack_ids=["test_pack"])

        mock_grant_manager = MagicMock()
        mock_grant_manager.check.return_value = _GrantResult(allowed=True, config={})

        mock_container = MagicMock()
        mock_container.get_or_none.return_value = None

        import core_runtime.capability_grant_manager as cgm_mod
        import core_runtime.di_container as di_mod

        orig_grant = getattr(cgm_mod, "get_capability_grant_manager", None)
        orig_container = getattr(di_mod, "get_container", None)
        cgm_mod.get_capability_grant_manager = lambda: mock_grant_manager
        di_mod.get_container = lambda: mock_container
        try:
            result = host._desktop_issue_token({"pack_id": "test_pack"})
            self.assertEqual(result["status_code"], 503)
            self.assertIn("not available", result["error"])
        finally:
            if orig_grant:
                cgm_mod.get_capability_grant_manager = orig_grant
            if orig_container:
                di_mod.get_container = orig_container

    def test_success(self):
        """正常リクエスト → token, port, expires_in が返る。"""
        host = _StubHost(valid_pack_ids=["test_pack"])

        mock_grant_manager = MagicMock()
        mock_grant_manager.check.return_value = _GrantResult(allowed=True, config={})

        mock_container = MagicMock()
        mock_container.get_or_none.return_value = _MockHandler()

        import core_runtime.capability_grant_manager as cgm_mod
        import core_runtime.di_container as di_mod

        orig_grant = getattr(cgm_mod, "get_capability_grant_manager", None)
        orig_container = getattr(di_mod, "get_container", None)
        cgm_mod.get_capability_grant_manager = lambda: mock_grant_manager
        di_mod.get_container = lambda: mock_container
        try:
            result = host._desktop_issue_token({"pack_id": "test_pack"})
            self.assertNotIn("status_code", result)
            self.assertEqual(result["token"], "test-token-abc123")
            self.assertEqual(result["port"], 8765)
            self.assertEqual(result["expires_in"], 3600)
        finally:
            if orig_grant:
                cgm_mod.get_capability_grant_manager = orig_grant
            if orig_container:
                di_mod.get_container = orig_container

    def test_handler_error(self):
        """handler がエラーを返す場合 → 403。"""
        host = _StubHost(valid_pack_ids=["test_pack"])

        mock_grant_manager = MagicMock()
        mock_grant_manager.check.return_value = _GrantResult(allowed=True, config={})

        mock_container = MagicMock()
        mock_container.get_or_none.return_value = _MockHandlerError()

        import core_runtime.capability_grant_manager as cgm_mod
        import core_runtime.di_container as di_mod

        orig_grant = getattr(cgm_mod, "get_capability_grant_manager", None)
        orig_container = getattr(di_mod, "get_container", None)
        cgm_mod.get_capability_grant_manager = lambda: mock_grant_manager
        di_mod.get_container = lambda: mock_container
        try:
            result = host._desktop_issue_token({"pack_id": "test_pack"})
            self.assertEqual(result["status_code"], 403)
            self.assertIn("not configured", result["error"])
        finally:
            if orig_grant:
                cgm_mod.get_capability_grant_manager = orig_grant
            if orig_container:
                di_mod.get_container = orig_container


if __name__ == "__main__":
    unittest.main()
