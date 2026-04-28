from __future__ import annotations

import os
import sys
import unittest
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


if __name__ == "__main__":
    unittest.main()
