from __future__ import annotations

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

    def test_browser_surface_is_default(self):
        from defaultspack.native_webview import open_desktop_surface

        with patch.dict(os.environ, {"RUMI_DEFAULTSPACK_OPEN_BROWSER": "1"}, clear=True):
            with patch("webbrowser.open") as mock_open:
                result = open_desktop_surface("http://127.0.0.1:8766/")

        self.assertEqual(result, "browser")
        mock_open.assert_called_once_with("http://127.0.0.1:8766/")

    def test_webview_surface_falls_back_when_optional_dependency_is_missing(self):
        from defaultspack.native_webview import open_desktop_surface

        with patch.dict(os.environ, {"RUMI_DEFAULTSPACK_OPEN_BROWSER": "1", "RUMI_DEFAULTSPACK_SURFACE": "webview"}, clear=True):
            with patch.dict(sys.modules, {"webview": None}):
                with patch("webbrowser.open") as mock_open:
                    result = open_desktop_surface("http://127.0.0.1:8766/")

        self.assertEqual(result, "webview_unavailable")
        mock_open.assert_called_once_with("http://127.0.0.1:8766/")

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
                    with patch("defaultspack.native_webview.open_desktop_surface", return_value="webview"):
                        result = desktop_app.main()

        self.assertEqual(result, 0)
        self.assertTrue(fake_server.started)
        self.assertTrue(fake_server.stopped)

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


if __name__ == "__main__":
    unittest.main()
