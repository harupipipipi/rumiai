from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from typing import Any


class CdpClient:
    """Minimal Chrome DevTools Protocol client.

    HTTP endpoints work with only the standard library. Websocket commands are
    best-effort and only run when a websocket implementation is installed or
    injected by a test.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9222,
        *,
        timeout: float = 2.0,
        websocket_factory: Any | None = None,
    ) -> None:
        self.host = host
        self.port = int(port)
        self.timeout = float(timeout)
        self.websocket_factory = websocket_factory

    @property
    def base_url(self) -> str:
        return "http://{}:{}".format(self.host, self.port)

    def version(self) -> dict[str, Any]:
        return self._json("/json/version")

    def list_tabs(self) -> list[dict[str, Any]]:
        value = self._json("/json")
        return value if isinstance(value, list) else []

    def new_tab(self, url: str = "about:blank") -> dict[str, Any]:
        quoted = urllib.parse.quote(url or "about:blank", safe=":/?#[]@!$&'()*+,;=%")
        path = "/json/new?{}".format(quoted)
        try:
            return {"ok": True, "tab": self._json(path, method="PUT")}
        except Exception:
            return {"ok": True, "tab": self._json(path)}

    def activate_tab(self, tab_id: str) -> dict[str, Any]:
        return {"ok": True, "response": self._text("/json/activate/{}".format(urllib.parse.quote(str(tab_id), safe="")))}

    def close_tab(self, tab_id: str) -> dict[str, Any]:
        return {"ok": True, "response": self._text("/json/close/{}".format(urllib.parse.quote(str(tab_id), safe="")))}

    def navigate(self, tab_id: str | None, url: str) -> dict[str, Any]:
        return self.command(tab_id, "Page.navigate", {"url": url})

    def evaluate(self, tab_id: str | None, expression: str) -> dict[str, Any]:
        response = self.command(
            tab_id,
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": False},
        )
        if not response.get("ok"):
            return response
        remote = response.get("response", {}).get("result", {}).get("result", {})
        if "value" in remote:
            return {"ok": True, "value": remote.get("value"), "response": response.get("response")}
        if "description" in remote:
            return {"ok": True, "value": remote.get("description"), "response": response.get("response")}
        return {"ok": True, "value": None, "response": response.get("response")}

    def snapshot(self, tab_id: str | None = None) -> dict[str, Any]:
        evaluated = self.evaluate(tab_id, _SNAPSHOT_JS)
        if not evaluated.get("ok"):
            return evaluated
        value = evaluated.get("value")
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except Exception:
                return {"ok": False, "reason": "snapshot_decode_failed", "value": evaluated.get("value")}
        if not isinstance(value, dict):
            return {"ok": False, "reason": "snapshot_result_not_object", "value": value}
        return {"ok": True, "snapshot": value}

    def screenshot(self, tab_id: str | None = None, *, format: str = "png", quality: int | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"format": format}
        if quality is not None:
            params["quality"] = int(quality)
        response = self.command(tab_id, "Page.captureScreenshot", params)
        if not response.get("ok"):
            return response
        data = response.get("response", {}).get("result", {}).get("data")
        if not isinstance(data, str) or not data:
            return {"ok": False, "reason": "screenshot_data_missing", "response": response.get("response")}
        return {"ok": True, "data": data, "mime_type": "image/jpeg" if format == "jpeg" else "image/png"}

    def command(self, tab_id: str | None, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        tab = self._find_tab(tab_id)
        if not tab:
            return {"ok": False, "reason": "tab_not_found", "tab_id": tab_id}
        ws_url = tab.get("webSocketDebuggerUrl")
        if not ws_url:
            return {"ok": False, "reason": "websocket_url_missing", "tab_id": tab.get("id")}
        factory = self._websocket_factory()
        if factory is None:
            return {"ok": False, "reason": "websocket_dependency_missing", "tab_id": tab.get("id")}
        payload = {"id": int(time.time() * 1000) % 1000000000, "method": method, "params": params or {}}
        sock = None
        try:
            sock = factory(ws_url, timeout=self.timeout)
            sock.send(json.dumps(payload))
            deadline = time.time() + self.timeout
            while time.time() < deadline:
                message = sock.recv()
                decoded = json.loads(message)
                if decoded.get("id") == payload["id"]:
                    if "error" in decoded:
                        return {"ok": False, "reason": "cdp_error", "error": decoded.get("error"), "response": decoded}
                    return {"ok": True, "response": decoded}
            return {"ok": False, "reason": "websocket_timeout", "method": method}
        except Exception as exc:
            return {"ok": False, "reason": "websocket_failed", "error": str(exc), "method": method}
        finally:
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass

    def _find_tab(self, tab_id: str | None) -> dict[str, Any] | None:
        tabs = self.list_tabs()
        pages = [tab for tab in tabs if tab.get("type") in {None, "page"}]
        if tab_id is None:
            return pages[0] if pages else (tabs[0] if tabs else None)
        for tab in tabs:
            if str(tab.get("id")) == str(tab_id):
                return tab
        return None

    def _json(self, path: str, *, method: str = "GET") -> Any:
        text = self._text(path, method=method)
        return json.loads(text or "null")

    def _text(self, path: str, *, method: str = "GET") -> str:
        url = self.base_url + path
        request = urllib.request.Request(url, method=method)
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            data = response.read()
        return data.decode("utf-8")

    def _websocket_factory(self) -> Any | None:
        if self.websocket_factory is not None:
            return self.websocket_factory
        try:
            import websocket  # type: ignore

            return websocket.create_connection
        except Exception:
            return None


_SNAPSHOT_JS = r"""
(() => {
  const roleFor = (el) => {
    const explicit = el.getAttribute('role');
    if (explicit) return explicit;
    const tag = el.tagName.toLowerCase();
    if (tag === 'a') return 'link';
    if (tag === 'button') return 'button';
    if (tag === 'input') {
      const type = (el.getAttribute('type') || 'text').toLowerCase();
      if (type === 'checkbox') return 'checkbox';
      if (type === 'radio') return 'radio';
      if (type === 'submit' || type === 'button') return 'button';
      return 'textbox';
    }
    if (tag === 'textarea') return 'textbox';
    if (tag === 'select') return 'combobox';
    return tag;
  };
  const selectorFor = (el) => {
    if (el.id) return '#' + CSS.escape(el.id);
    const parts = [];
    let node = el;
    while (node && node.nodeType === Node.ELEMENT_NODE && parts.length < 5) {
      let part = node.tagName.toLowerCase();
      if (node.classList && node.classList.length) {
        part += '.' + Array.from(node.classList).slice(0, 2).map((item) => CSS.escape(item)).join('.');
      }
      const parent = node.parentElement;
      if (parent) {
        const siblings = Array.from(parent.children).filter((child) => child.tagName === node.tagName);
        if (siblings.length > 1) part += `:nth-of-type(${siblings.indexOf(node) + 1})`;
      }
      parts.unshift(part);
      node = parent;
    }
    return parts.join(' > ');
  };
  const textFor = (el) => (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 240);
  const nameFor = (el) => (
    el.getAttribute('aria-label') ||
    el.getAttribute('title') ||
    el.getAttribute('alt') ||
    el.getAttribute('placeholder') ||
    el.getAttribute('value') ||
    textFor(el)
  || '').trim().slice(0, 240);
  const candidates = Array.from(document.querySelectorAll(
    'a,button,input,textarea,select,summary,[role],[aria-label],[contenteditable],[tabindex]'
  ));
  const elements = candidates.map((el, index) => {
    const rect = el.getBoundingClientRect();
    return {
      index,
      role: roleFor(el),
      name: nameFor(el),
      text: textFor(el),
      selector: selectorFor(el),
      tag: el.tagName.toLowerCase(),
      interactive: true,
      bounds: {
        x: Math.round(rect.left + window.scrollX),
        y: Math.round(rect.top + window.scrollY),
        width: Math.round(rect.width),
        height: Math.round(rect.height)
      }
    };
  });
  return JSON.stringify({
    url: location.href,
    title: document.title,
    captured_at: new Date().toISOString(),
    viewport: {
      width: window.innerWidth,
      height: window.innerHeight,
      scroll_x: window.scrollX,
      scroll_y: window.scrollY
    },
    elements
  });
})()
"""
