"""Small Chrome DevTools Protocol client.

The client intentionally depends only on the Python standard library so the
ComputerSeat driver can stay import-safe in normal desktop installations. It
supports HTTP discovery and optional websocket method calls when the
``websocket-client`` package is installed.
"""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass
class CDPTab:
    id: str
    title: str
    url: str
    web_socket_debugger_url: str


class BrowserCDPClient:
    """Minimal CDP client for a running remote-debugging browser."""

    def __init__(self, endpoint: str | None = None, *, timeout: float = 3.0) -> None:
        self.endpoint = (endpoint or os.getenv("RUMI_BROWSER_CDP_ENDPOINT") or "").rstrip("/")
        self.timeout = timeout

    def is_available(self) -> bool:
        if not self.endpoint:
            return False
        try:
            self.list_tabs()
            return True
        except Exception:
            return False

    def list_tabs(self) -> list[CDPTab]:
        raw_tabs = self._get_json("/json")
        tabs: list[CDPTab] = []
        for raw in raw_tabs if isinstance(raw_tabs, list) else []:
            if not isinstance(raw, dict):
                continue
            ws_url = str(raw.get("webSocketDebuggerUrl") or "")
            if not ws_url:
                continue
            tabs.append(CDPTab(
                id=str(raw.get("id") or ""),
                title=str(raw.get("title") or ""),
                url=str(raw.get("url") or ""),
                web_socket_debugger_url=ws_url,
            ))
        return tabs

    def resolve_tab(self, *, tab_id: str | int | None = None, url: str | None = None) -> CDPTab | None:
        tabs = self.list_tabs()
        if tab_id is not None:
            wanted = str(tab_id)
            for tab in tabs:
                if tab.id == wanted:
                    return tab
        if url:
            for tab in tabs:
                if url in tab.url:
                    return tab
        return tabs[0] if tabs else None

    def call(self, tab: CDPTab, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            import websocket  # type: ignore[import]
        except Exception as exc:
            raise RuntimeError("websocket-client is required for CDP method calls") from exc

        ws = websocket.create_connection(tab.web_socket_debugger_url, timeout=self.timeout)
        try:
            message_id = int(time.time() * 1000)
            ws.send(json.dumps({"id": message_id, "method": method, "params": params or {}}))
            while True:
                response = json.loads(ws.recv())
                if response.get("id") == message_id:
                    if "error" in response:
                        raise RuntimeError(str(response["error"]))
                    return response.get("result") if isinstance(response.get("result"), dict) else {}
        finally:
            ws.close()

    def capture_screenshot(self, tab: CDPTab) -> dict[str, Any]:
        result = self.call(tab, "Page.captureScreenshot", {"format": "png", "fromSurface": True})
        data = str(result.get("data") or "")
        return {
            "data_url": f"data:image/png;base64,{data}" if data else "",
            "image_size": {},
            "coordinate_system": "viewport_pixels",
            "method": "browser_cdp",
        }

    def dom_snapshot(self, tab: CDPTab) -> dict[str, Any]:
        result = self.call(tab, "DOM.getDocument", {"depth": 2, "pierce": True})
        return result.get("root") if isinstance(result.get("root"), dict) else result

    def click(self, tab: CDPTab, x: int, y: int, button: str = "left") -> None:
        cdp_button = "right" if button == "right" else "middle" if button == "middle" else "left"
        base = {"x": x, "y": y, "button": cdp_button, "clickCount": 1}
        self.call(tab, "Input.dispatchMouseEvent", {"type": "mousePressed", **base})
        self.call(tab, "Input.dispatchMouseEvent", {"type": "mouseReleased", **base})

    def type_text(self, tab: CDPTab, text: str) -> None:
        self.call(tab, "Input.insertText", {"text": text})

    def press_key(self, tab: CDPTab, key: str) -> None:
        self.call(tab, "Input.dispatchKeyEvent", {"type": "keyDown", "key": key})
        self.call(tab, "Input.dispatchKeyEvent", {"type": "keyUp", "key": key})

    def scroll(self, tab: CDPTab, x: int, y: int, direction: str, clicks: int) -> None:
        amount = max(1, int(clicks or 1)) * 120
        delta_x = -amount if direction == "left" else amount if direction == "right" else 0
        delta_y = -amount if direction == "up" else amount if direction == "down" else 0
        self.call(tab, "Input.dispatchMouseEvent", {
            "type": "mouseWheel",
            "x": x,
            "y": y,
            "deltaX": delta_x,
            "deltaY": delta_y,
        })

    def _get_json(self, path: str) -> Any:
        if not self.endpoint:
            raise RuntimeError("RUMI_BROWSER_CDP_ENDPOINT is not configured")
        with urllib.request.urlopen(f"{self.endpoint}{path}", timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))


def data_url_to_bytes(data_url: str) -> bytes:
    _, _, payload = data_url.partition(",")
    return base64.b64decode(payload) if payload else b""
