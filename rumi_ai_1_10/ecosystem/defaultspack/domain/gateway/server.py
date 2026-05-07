from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .delivery import GatewayDelivery


class GatewayServer:
    def __init__(self) -> None:
        self.host = "127.0.0.1"
        self.port = 18789
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.delivery = GatewayDelivery()

    def start(self, host: str = "127.0.0.1", port: int = 18789) -> dict[str, Any]:
        if self._httpd is not None:
            return self.status()
        self.host = host
        self.port = int(port)
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                if self.path.endswith("/status") or self.path == "/":
                    self._json(200, outer.status())
                    return
                self._json(404, {"error": "not found"})

            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("content-length", "0") or 0)
                raw = self.rfile.read(length).decode("utf-8") if length else "{}"
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    payload = {}
                message = outer.delivery.publish("gateway.message", payload)
                self._json(200, {"status": "ok", "message": message})

            def log_message(self, format, *args):  # noqa: A003
                return

            def _json(self, status: int, payload: dict):
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self._httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        self.port = int(self._httpd.server_address[1])
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self.status()

    def stop(self) -> dict[str, Any]:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        self._thread = None
        return self.status()

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self._httpd is not None,
            "host": self.host,
            "port": self.port,
            "message_count": len(self.delivery.messages),
        }


_server = GatewayServer()


def get_gateway_server() -> GatewayServer:
    return _server
