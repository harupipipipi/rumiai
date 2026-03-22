"""ControlPanelHandlersMixin の基本テスト"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# テスト対象のインポートパスを解決
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from core_runtime.api.control_panel_handlers import ControlPanelHandlersMixin


class _FakeHandler(ControlPanelHandlersMixin):
    """テスト用のフェイクハンドラ（Mixin を単体テストするため）"""
    kernel = None
    app_lifecycle_manager = None


class TestPanelGetDashboard(unittest.TestCase):
    """GET /api/panel/dashboard のレスポンス形式テスト"""

    def test_dashboard_returns_required_keys(self):
        handler = _FakeHandler()
        # kernel なしでも動作する（数値は 0）
        result = handler._panel_get_dashboard()
        self.assertIn("packs", result)
        self.assertIn("flows", result)
        self.assertIn("kernel", result)
        self.assertIn("profile", result)

    def test_dashboard_packs_structure(self):
        handler = _FakeHandler()
        result = handler._panel_get_dashboard()
        packs = result["packs"]
        self.assertIn("total", packs)
        self.assertIn("enabled", packs)
        self.assertIn("disabled", packs)
        self.assertIsInstance(packs["total"], int)

    def test_dashboard_flows_structure(self):
        handler = _FakeHandler()
        result = handler._panel_get_dashboard()
        flows = result["flows"]
        self.assertIn("total", flows)
        self.assertIsInstance(flows["total"], int)


class TestPanelGetPacks(unittest.TestCase):
    """GET /api/panel/packs のレスポンス形式テスト"""

    def test_packs_returns_list_and_count(self):
        handler = _FakeHandler()
        result = handler._panel_get_packs()
        self.assertIn("packs", result)
        self.assertIn("count", result)
        self.assertIsInstance(result["packs"], list)
        self.assertEqual(result["count"], len(result["packs"]))


class TestPanelGetFlows(unittest.TestCase):
    """GET /api/panel/flows のレスポンス形式テスト"""

    def test_flows_returns_list_and_count_without_kernel(self):
        handler = _FakeHandler()
        result = handler._panel_get_flows()
        self.assertIn("flows", result)
        self.assertIn("count", result)
        self.assertIsInstance(result["flows"], list)
        # kernel なしなので空リスト
        self.assertEqual(result["count"], 0)


class TestPanelGetFlowDetail(unittest.TestCase):
    """GET /api/panel/flows/{id} のレスポンス形式テスト"""

    def test_flow_detail_without_kernel_returns_error(self):
        handler = _FakeHandler()
        result = handler._panel_get_flow_detail("test.flow")
        self.assertIn("error", result)
        self.assertIn("status_code", result)
        self.assertEqual(result["status_code"], 503)


class TestPanelCreateFlow(unittest.TestCase):
    """POST /api/panel/flows のバリデーションテスト"""

    def test_create_flow_missing_flow_id(self):
        handler = _FakeHandler()
        result = handler._panel_create_flow({"yaml_content": "test: true"})
        self.assertIn("error", result)
        self.assertEqual(result["status_code"], 400)

    def test_create_flow_missing_yaml_content(self):
        handler = _FakeHandler()
        result = handler._panel_create_flow({"flow_id": "test_flow"})
        self.assertIn("error", result)
        self.assertEqual(result["status_code"], 400)

    def test_create_flow_invalid_flow_id(self):
        handler = _FakeHandler()
        result = handler._panel_create_flow({
            "flow_id": "../../../etc/passwd",
            "yaml_content": "test: true",
        })
        self.assertIn("error", result)
        self.assertEqual(result["status_code"], 400)


class TestPanelGetVersion(unittest.TestCase):
    """GET /api/panel/version のレスポンス形式テスト"""

    def test_version_returns_required_keys(self):
        handler = _FakeHandler()
        result = handler._panel_get_version()
        self.assertIn("kernel_version", result)
        self.assertIn("python_version", result)
        self.assertIn("platform", result)
        self.assertIsInstance(result["kernel_version"], str)
        self.assertIsInstance(result["python_version"], str)


class TestPanelGetProfile(unittest.TestCase):
    """GET /api/panel/settings/profile のテスト"""

    def test_profile_not_found_returns_error(self):
        handler = _FakeHandler()
        # profile.json が存在しない場合
        with patch.object(
            ControlPanelHandlersMixin,
            "_panel_read_profile",
            return_value=None,
        ):
            result = handler._panel_get_profile()
            self.assertIn("error", result)
            self.assertEqual(result["status_code"], 404)

    def test_profile_found_returns_data(self):
        handler = _FakeHandler()
        mock_profile = {"username": "test", "language": "ja"}
        with patch.object(
            ControlPanelHandlersMixin,
            "_panel_read_profile",
            return_value=mock_profile,
        ):
            result = handler._panel_get_profile()
            self.assertIn("profile", result)
            self.assertEqual(result["profile"]["username"], "test")


class TestPanelRestartKernel(unittest.TestCase):
    """POST /api/panel/kernel/restart のレスポンス形式テスト"""

    @patch("threading.Thread")
    def test_restart_returns_restarting(self, mock_thread_cls):
        mock_instance = MagicMock()
        mock_thread_cls.return_value = mock_instance
        handler = _FakeHandler()
        result = handler._panel_restart_kernel()
        self.assertIn("restarting", result)
        self.assertTrue(result["restarting"])
        mock_instance.start.assert_called_once()


class TestPanelEnableDisablePack(unittest.TestCase):
    """POST /api/panel/packs/{id}/enable|disable のテスト"""

    @patch("core_runtime.api.control_panel_handlers.discover_pack_locations")
    def test_enable_pack_not_found(self, mock_discover):
        mock_discover.return_value = []
        handler = _FakeHandler()
        result = handler._panel_enable_pack("nonexistent_pack")
        self.assertIn("error", result)
        self.assertEqual(result["status_code"], 404)


if __name__ == "__main__":
    unittest.main()
