from __future__ import annotations

import os
import webbrowser
from typing import Literal

SurfaceResult = Literal["disabled", "browser", "webview", "webview_unavailable"]


def open_desktop_surface(url: str, title: str = "Rumi Defaultspack") -> SurfaceResult:
    """Open the defaultspack shell without coupling the pack to one UI runtime."""
    if os.environ.get("RUMI_DEFAULTSPACK_OPEN_BROWSER", "1") == "0":
        return "disabled"

    surface = os.environ.get("RUMI_DEFAULTSPACK_SURFACE", "webview").strip().lower()
    if surface == "webview":
        try:
            import webview  # type: ignore[import-not-found]
        except Exception:
            return "webview_unavailable"

        window = webview.create_window(title, url)
        webview.start()
        return "webview" if window is not None else "webview_unavailable"

    webbrowser.open(url)
    return "browser"
