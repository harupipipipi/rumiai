from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from domain.runtime_config import gateway_config
from .auth import LocalGatewayAuth
from .delivery import GatewayDelivery


class GatewayServer:
    def __init__(self) -> None:
        self.host = "127.0.0.1"
        self.port = 18789
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.delivery = GatewayDelivery()
        self.auth = LocalGatewayAuth()

    def start(self, host: str = "127.0.0.1", port: int = 18789) -> dict[str, Any]:
        if self._httpd is not None:
            return self.status()
        config = gateway_config()
        requested_host = str(host or config.get("host") or "127.0.0.1")
        if not _is_loopback_host(requested_host) and config.get("allow_external") is not True:
            return {"enabled": False, "status": "error", "error": "gateway external bind disabled", "host": self.host, "port": self.port}
        self.host = requested_host
        self.port = int(port or config.get("port") or 18789)
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                if self.path.endswith("/status") or self.path == "/":
                    self._json(200, outer.status())
                    return
                self._json(404, {"error": "not found"})

            def do_POST(self):  # noqa: N802
                if not outer._authorized(self):
                    self._json(401, {"status": "error", "error": "unauthorized"})
                    return
                length = int(self.headers.get("content-length", "0") or 0)
                if length > 1024 * 1024:
                    self._json(413, {"status": "error", "error": "request too large"})
                    return
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
            "auth_required": True,
        }

    def _authorized(self, request: BaseHTTPRequestHandler) -> bool:
        header = request.headers.get("authorization", "")
        token = ""
        if header.lower().startswith("bearer "):
            token = header.split(" ", 1)[1].strip()
        token = token or request.headers.get("x-rumi-gateway-token", "")
        return self.auth.check(token)


_server = GatewayServer()


def get_gateway_server() -> GatewayServer:
    return _server


def _is_loopback_host(host: str) -> bool:
    normalized = str(host or "").strip().lower()
    return normalized in {"127.0.0.1", "localhost", "::1"}
