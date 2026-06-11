from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from importlib import import_module
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


class TestDefaultspackDesktopSurface(unittest.TestCase):
    def test_surface_can_be_disabled_for_smoke_tests(self):
        from defaultspack.native_webview import open_desktop_surface

        with patch.dict(os.environ, {"RUMI_DEFAULTSPACK_OPEN_BROWSER": "0"}):
            result = open_desktop_surface("http://127.0.0.1:8766/")

        self.assertEqual(result, "disabled")

    def test_webview_surface_is_default_and_does_not_open_browser_when_missing(self):
        from defaultspack.native_webview import open_desktop_surface

        with patch.dict(os.environ, {"RUMI_DEFAULTSPACK_OPEN_BROWSER": "1"}, clear=True):
            with patch.dict(sys.modules, {"webview": None}):
                with patch("webbrowser.open") as mock_open:
                    result = open_desktop_surface("http://127.0.0.1:8766/")

        self.assertEqual(result, "webview_unavailable")
        mock_open.assert_not_called()

    def test_webview_surface_falls_back_when_optional_dependency_is_missing(self):
        from defaultspack.native_webview import open_desktop_surface

        with patch.dict(os.environ, {"RUMI_DEFAULTSPACK_OPEN_BROWSER": "1", "RUMI_DEFAULTSPACK_SURFACE": "webview"}, clear=True):
            with patch.dict(sys.modules, {"webview": None}):
                with patch("webbrowser.open") as mock_open:
                    result = open_desktop_surface("http://127.0.0.1:8766/")

        self.assertEqual(result, "webview_unavailable")
        mock_open.assert_not_called()

    def test_desktop_app_main_stops_server_after_blocking_webview_closes(self):
        from defaultspack import desktop_app

        class FakeServer:
            def __init__(self, facade=None):
                self.started = False
                self.stopped = False

            def start(self):
                self.started = True

            def stop(self):
                self.stopped = True

        fake_server = FakeServer()

        with patch.dict(os.environ, {"RUMI_DEFAULTSPACK_OPEN_BROWSER": "1", "RUMI_DEFAULTSPACK_SURFACE": "webview"}, clear=True):
            with patch("transport.http.DefaultsHttpServer", return_value=fake_server):
                with patch.object(desktop_app, "_wait_until_ready", return_value=True):
                    with patch.object(desktop_app, "_wait_until_chat_ready", return_value=True):
                        with patch("defaultspack.native_webview.open_desktop_surface", return_value="webview"):
                            result = desktop_app.main()

        self.assertEqual(result, 0)
        self.assertTrue(fake_server.started)
        self.assertTrue(fake_server.stopped)

    def test_desktop_app_main_logs_and_exits_when_existing_server_is_reused(self):
        from defaultspack import desktop_app

        class PortBusyServer:
            def __init__(self, facade=None):
                self.stopped = False

            def start(self):
                raise OSError("address already in use")

            def stop(self):
                self.stopped = True

        fake_server = PortBusyServer()

        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "defaultspack-launch.jsonl"
            env = {
                "DEFAULTS_HTTP_PORT": "8766",
                "RUMI_DEFAULTSPACK_LAUNCH_LOG": str(log_path),
                "RUMI_DEFAULTSPACK_OPEN_BROWSER": "1",
                "RUMI_DEFAULTSPACK_PORT": "8766",
            }
            with patch.dict(os.environ, env, clear=True):
                with patch("transport.http.DefaultsHttpServer", return_value=fake_server):
                    with patch.object(desktop_app, "_wait_until_ready", return_value=True):
                        with patch.object(desktop_app, "_wait_until_chat_ready", return_value=True):
                            with patch.object(
                                desktop_app,
                                "_port_owner_snapshot",
                                return_value=[{"pid": "123", "command": "python3"}],
                            ):
                                with patch("defaultspack.native_webview.open_desktop_surface", return_value="browser"):
                                    result = desktop_app.main()

            self.assertEqual(result, 0)
            self.assertFalse(fake_server.stopped)
            events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]

        event_names = [event["event"] for event in events]
        self.assertIn("server_start_oserror", event_names)
        self.assertIn("duplicate_launcher_exit", event_names)
        busy_event = next(event for event in events if event["event"] == "server_start_oserror")
        self.assertTrue(busy_event["existing_ready"])
        self.assertEqual(busy_event["port_owners"], [{"pid": "123", "command": "python3"}])
        self.assertNotIn("RUMI_API_TOKEN", events[0]["env"])

    def test_managed_pack_root_alias_supports_ecosystem_defaultspack_imports(self):
        from defaultspack import desktop_app

        saved_modules = {
            name: module
            for name, module in sys.modules.items()
            if name == "ecosystem" or name.startswith("ecosystem.defaultspack")
        }
        try:
            for name in list(sys.modules):
                if name == "ecosystem" or name.startswith("ecosystem.defaultspack"):
                    sys.modules.pop(name, None)

            with tempfile.TemporaryDirectory() as tmp:
                pack_root = Path(tmp)
                domain_dir = pack_root / "domain"
                domain_dir.mkdir()
                (domain_dir / "__init__.py").write_text("", encoding="utf-8")
                (domain_dir / "managed_marker.py").write_text(
                    "VALUE = 'managed-defaultspack'\n",
                    encoding="utf-8",
                )

                desktop_app._install_ecosystem_defaultspack_alias(pack_root)
                module = import_module("ecosystem.defaultspack.domain.managed_marker")

            self.assertEqual(module.VALUE, "managed-defaultspack")
        finally:
            for name in list(sys.modules):
                if name == "ecosystem" or name.startswith("ecosystem.defaultspack"):
                    sys.modules.pop(name, None)
            sys.modules.update(saved_modules)

    def test_managed_pack_alias_keeps_sibling_tools_pack_visible(self):
        from defaultspack import desktop_app

        saved_modules = {
            name: module
            for name, module in sys.modules.items()
            if name == "ecosystem" or name.startswith("ecosystem.")
        }
        try:
            for name in list(sys.modules):
                if name == "ecosystem" or name.startswith("ecosystem."):
                    sys.modules.pop(name, None)

            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                app_dir = tmp_path / "app"
                tools_pkg = app_dir / "ecosystem" / "rumi_default_tools_pack"
                tool_dir = tools_pkg / "domain" / "tool"
                tool_dir.mkdir(parents=True)
                (tools_pkg / "__init__.py").write_text("", encoding="utf-8")
                (tools_pkg / "domain" / "__init__.py").write_text("", encoding="utf-8")
                (tool_dir / "__init__.py").write_text("", encoding="utf-8")
                (tool_dir / "marker.py").write_text("VALUE = 'tools-pack'\n", encoding="utf-8")

                pack_root = tmp_path / "user_data" / "packs" / "defaultspack" / "versions" / "2.0.0"
                (pack_root / "domain").mkdir(parents=True)
                (pack_root / "domain" / "__init__.py").write_text("", encoding="utf-8")
                (pack_root / "domain" / "managed_marker.py").write_text(
                    "VALUE = 'managed-defaultspack'\n",
                    encoding="utf-8",
                )

                with patch.dict(os.environ, {"RUMI_APP_DIR": str(app_dir)}, clear=False):
                    desktop_app._install_ecosystem_defaultspack_alias(pack_root)
                    managed = import_module("ecosystem.defaultspack.domain.managed_marker")
                    tools = import_module("ecosystem.rumi_default_tools_pack.domain.tool.marker")

            self.assertEqual(managed.VALUE, "managed-defaultspack")
            self.assertEqual(tools.VALUE, "tools-pack")
        finally:
            for name in list(sys.modules):
                if name == "ecosystem" or name.startswith("ecosystem."):
                    sys.modules.pop(name, None)
            sys.modules.update(saved_modules)

    def test_legacy_pack_alias_keeps_resource_ecosystem_visible(self):
        from defaultspack import desktop_app

        saved_modules = {
            name: module
            for name, module in sys.modules.items()
            if name == "ecosystem" or name.startswith("ecosystem.")
        }
        try:
            for name in list(sys.modules):
                if name == "ecosystem" or name.startswith("ecosystem."):
                    sys.modules.pop(name, None)

            with tempfile.TemporaryDirectory() as tmp:
                app_dir = Path(tmp) / "app"
                ecosystem_dir = app_dir / "ecosystem"
                pack_root = ecosystem_dir / "defaultspack"
                default_domain = pack_root / "domain"
                tools_pkg = ecosystem_dir / "rumi_default_tools_pack"
                tool_dir = tools_pkg / "domain" / "tool"
                default_domain.mkdir(parents=True)
                tool_dir.mkdir(parents=True)
                (default_domain / "__init__.py").write_text("", encoding="utf-8")
                (default_domain / "legacy_marker.py").write_text(
                    "VALUE = 'legacy-defaultspack'\n",
                    encoding="utf-8",
                )
                (tools_pkg / "__init__.py").write_text("", encoding="utf-8")
                (tools_pkg / "domain" / "__init__.py").write_text("", encoding="utf-8")
                (tool_dir / "__init__.py").write_text("", encoding="utf-8")
                (tool_dir / "marker.py").write_text("VALUE = 'legacy-tools-pack'\n", encoding="utf-8")

                with patch.dict(os.environ, {"RUMI_APP_DIR": str(app_dir)}, clear=False):
                    desktop_app._install_ecosystem_defaultspack_alias(pack_root)
                    legacy_default = import_module("ecosystem.defaultspack.domain.legacy_marker")
                    legacy_tools = import_module("ecosystem.rumi_default_tools_pack.domain.tool.marker")

            self.assertEqual(legacy_default.VALUE, "legacy-defaultspack")
            self.assertEqual(legacy_tools.VALUE, "legacy-tools-pack")
        finally:
            for name in list(sys.modules):
                if name == "ecosystem" or name.startswith("ecosystem."):
                    sys.modules.pop(name, None)
            sys.modules.update(saved_modules)


if __name__ == "__main__":
    unittest.main()
