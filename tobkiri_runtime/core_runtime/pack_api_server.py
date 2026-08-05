"""Finite localhost HTTP boundary for the captured Tobkiri Pack v4 runtime."""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Mapping, Protocol
from urllib.parse import urlparse

from .api.api_response import APIResponse
from .api.auth_gate import AuthGateMixin
from .api.http_response import ResponseWriterMixin
from .api.request_body import RequestBodyMixin
from .api.setup_handlers import SetupHandlersMixin
from .api.web_mounts import WebMountMixin
from .host_contract import host_contract_value
from .panel_auth import PanelAuthManager, get_panel_auth_manager
from tobkiri_host.errors import HostCoreError


logger = logging.getLogger(__name__)

THREAD_JOIN_TIMEOUT_SECONDS = 5
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_RETIRED_API_ROOTS = frozenset(
    {
        "auth",
        "authority",
        "capabilities",
        "containers",
        "desktop",
        "flows",
        "graphs",
        "integrations",
        "mobile",
        "network",
        "nodes",
        "packs",
        "panel",
        "pip",
        "privileges",
        "profiles",
        "routes",
        "runtime",
        "secrets",
        "stores",
        "units",
        "viewer",
        "webhooks",
    }
)


class DispatchSession(Protocol):
    """Captured Broker session exposed to the HTTP adapter."""

    def invoke(
        self,
        contract_id: str,
        operation_id: str,
        payload: Mapping[str, object],
        *,
        version_range: str = ">=1,<2",
    ) -> Mapping[str, object]:
        """Invoke one exact qualified operation through RequestBroker."""


class LifecyclePort(Protocol):
    """Read-only lifecycle surface required by the HTTP shell."""

    def check_setup_status(self) -> dict[str, object]:
        """Return canonical setup and readiness state."""

    def get_health(self) -> dict[str, object]:
        """Return current process health."""


@dataclass(frozen=True)
class RuntimeHTTPConfig:
    """Verified local-only server coordinates."""

    host: str
    port: int

    @classmethod
    def verify(cls, host: str, port: int) -> "RuntimeHTTPConfig":
        """Canonicalize a loopback request and reject network exposure."""

        if host.strip().lower() not in _LOOPBACK_HOSTS:
            raise ValueError("Pack v4 HTTP server is loopback-only")
        if not isinstance(port, int) or not 0 <= port <= 65535:
            raise ValueError("Pack v4 HTTP port must be between 0 and 65535")
        return cls(host="127.0.0.1", port=port)


class _PackThreadingHTTPServer(ThreadingHTTPServer):
    """Thread-per-request local server with bounded lifecycle semantics."""

    allow_reuse_address = True
    daemon_threads = True
    block_on_close = False
    request_queue_size = 128


class PackAPIHandler(
    ResponseWriterMixin,
    AuthGateMixin,
    RequestBodyMixin,
    SetupHandlersMixin,
    WebMountMixin,
    BaseHTTPRequestHandler,
):
    """Serve only health, setup, panel auth/static, and Pack v4 dispatch."""

    _CLIENT_DISCONNECT_EXCEPTIONS = (
        BrokenPipeError,
        ConnectionResetError,
        ConnectionAbortedError,
    )
    _panel_auth_manager: PanelAuthManager | None = None
    _dispatch_session: DispatchSession | None = None
    app_lifecycle_manager: LifecyclePort | None = None
    _runtime_port = 8765
    _request_auth_mode: str | None = None
    _panel_session: Mapping[str, object] | None = None
    _panel_session_cookie: str | None = None
    _raw_body_bytes = b""

    @staticmethod
    def canonical_v4_server_handler(
        *,
        panel_auth_manager: PanelAuthManager,
        dispatch_session: DispatchSession | None,
        app_lifecycle_manager: LifecyclePort | None,
    ) -> type["PackAPIHandler"]:
        """Create an isolated handler bound to one captured runtime session."""

        bound_panel_auth = panel_auth_manager
        bound_dispatch = dispatch_session
        bound_lifecycle = app_lifecycle_manager

        class BoundPackAPIHandler(PackAPIHandler):
            _panel_auth_manager = bound_panel_auth
            _dispatch_session = bound_dispatch
            app_lifecycle_manager = bound_lifecycle

        BoundPackAPIHandler.__name__ = "PackAPIHandlerV4Instance"
        return BoundPackAPIHandler

    def log_message(self, format: str, *args: object) -> None:
        """Write request logs after removing bootstrap query material."""

        sanitized = tuple(self._redact_log_value(value) for value in args)
        try:
            message = format % sanitized if sanitized else format
        except (TypeError, ValueError):
            message = " ".join(sanitized) if sanitized else format
        logger.info("API: %s", message)

    @staticmethod
    def _redact_log_value(value: object) -> str:
        return re.sub(
            r"([?&](?:token|code)=)[^&\s\"]+",
            r"\1[REDACTED]",
            "" if value is None else str(value),
            flags=re.IGNORECASE,
        )

    @staticmethod
    def _is_loopback_client(client_address: object) -> bool:
        if not isinstance(client_address, tuple) or not client_address:
            return False
        return str(client_address[0]).lower() in _LOOPBACK_HOSTS | {
            "::ffff:127.0.0.1"
        }

    def _reset_request_state(self) -> None:
        self._request_auth_mode = None
        self._panel_session = None
        self._panel_session_cookie = None
        self._raw_body_bytes = b""

    @classmethod
    def _get_cors_origin(cls, request_origin: str) -> str:
        """Allow only the exact local runtime origin."""

        allowed = {
            f"http://127.0.0.1:{cls._runtime_port}",
            f"http://localhost:{cls._runtime_port}",
        }
        return request_origin if request_origin in allowed else ""

    @staticmethod
    def _retired_api_path(path: str) -> bool:
        parts = path.strip("/").split("/")
        return len(parts) >= 2 and parts[0] == "api" and parts[1] in _RETIRED_API_ROOTS

    def _send_retired_api(self, path: str) -> None:
        self._send_response(
            APIResponse(
                False,
                data={
                    "api_version": "io.tobkiri.pack-api.v4",
                    "state": "legacy_api_retired",
                    "retired_route": path,
                    "write_set": [],
                },
                error="Legacy API route is retired; use an exact Pack v4 operation",
            ),
            410,
        )

    def _send_not_found(self) -> None:
        self._send_response(APIResponse(False, error="Not found"), 404)

    def _parse_object_body(self) -> dict[str, object] | None:
        """Parse one JSON object and reject every other JSON root type."""

        parsed: object = self._parse_body()
        if parsed is None:
            return None
        if not isinstance(parsed, dict) or any(
            not isinstance(key, str) for key in parsed
        ):
            self._send_response(
                APIResponse(False, error="Request body must be a JSON object"),
                400,
            )
            return None
        return {
            key: value for key, value in parsed.items() if isinstance(key, str)
        }

    def _send_mapping_result(self, result: Mapping[str, object]) -> None:
        error = result.get("error")
        status = result.get("status_code", 500 if error is not None else 200)
        status_code = status if isinstance(status, int) else 500
        if error is None:
            self._send_response(APIResponse(True, data=dict(result)), status_code)
            return
        self._send_response(
            APIResponse(
                False,
                data={
                    key: value
                    for key, value in result.items()
                    if key not in {"error", "status_code"}
                },
                error=str(error),
            ),
            status_code,
        )

    def _handle_health(self) -> None:
        lifecycle = self.__class__.app_lifecycle_manager
        health: dict[str, object] = (
            lifecycle.get_health()
            if lifecycle is not None
            else {
                "status": "ok",
                "needs_setup": True,
                "runtime_status": "starting",
            }
        )
        challenge = (
            self.headers.get("X-Rumi-Desktop-Health-Challenge", "")
            if hasattr(self, "headers")
            else ""
        )
        bootstrap_secret = host_contract_value("panel_bootstrap_secret")
        if challenge and bootstrap_secret:
            health["desktop_challenge_response"] = hmac.new(
                bootstrap_secret.encode("utf-8"),
                challenge.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
        self._send_response(APIResponse(True, data=health))

    def _handle_panel_bootstrap(self) -> None:
        manager = self._panel_auth_manager
        secret = self.headers.get("X-Rumi-Desktop-Bootstrap", "")
        if (
            manager is None
            or not self._is_loopback_client(self.client_address)
            or not manager.validate_bootstrap_secret(secret)
        ):
            self._discard_request_body()
            self._send_response(APIResponse(False, error="Unauthorized"), 401)
            return
        self._discard_request_body()
        self._send_response(APIResponse(True, data=manager.issue_login_code()))

    def _handle_panel_exchange(self, body: Mapping[str, object]) -> None:
        manager = self._panel_auth_manager
        if (
            not self._is_loopback_client(self.client_address)
            or not self._check_panel_origin()
        ):
            self._send_response(APIResponse(False, error="Forbidden origin"), 403)
            return
        code_value = body.get("code")
        code = code_value.strip() if isinstance(code_value, str) else ""
        exchange = manager.exchange_code(code) if manager is not None else None
        if exchange is None:
            self._send_response(APIResponse(False, error="Invalid or expired code"), 401)
            return
        cookie = self._build_set_cookie(
            "rumi_panel_session",
            str(exchange["session_id"]),
            path="/",
            max_age=int(exchange["expires_in"]),
            http_only=True,
        )
        self._send_response(
            APIResponse(
                True,
                data={
                    "csrf_token": exchange["csrf_token"],
                    "expires_in": exchange["expires_in"],
                },
            ),
            extra_headers=[("Set-Cookie", cookie)],
        )

    def _setup_pre_auth_allowed(self) -> bool:
        lifecycle = self.__class__.app_lifecycle_manager
        if lifecycle is None:
            return False
        try:
            return lifecycle.check_setup_status().get("needs_setup") is True
        except (OSError, RuntimeError, ValueError):
            logger.exception("Canonical setup state could not be verified")
            return False

    def _handle_setup_status(self) -> None:
        lifecycle = self.__class__.app_lifecycle_manager
        state: dict[str, object] = (
            lifecycle.check_setup_status()
            if lifecycle is not None
            else {
                "needs_setup": True,
                "reason": "lifecycle_manager_unavailable",
            }
        )
        self._send_response(APIResponse(True, data=state))

    def _handle_v4_dispatch(self, body: Mapping[str, object]) -> None:
        session = self._dispatch_session
        panel_session = self._panel_session
        if session is None:
            self._send_response(
                APIResponse(False, error="Captured v4 dispatch session is unavailable"),
                503,
            )
            return
        session_id_value = panel_session.get("session_id") if panel_session else None
        contract_value = body.get("contract_id")
        operation_value = body.get("operation_id")
        payload_value = body.get("payload")
        if (
            not isinstance(session_id_value, str)
            or not session_id_value
            or not isinstance(contract_value, str)
            or not contract_value.strip()
            or not isinstance(operation_value, str)
            or not operation_value.strip()
            or not isinstance(payload_value, dict)
            or any(not isinstance(key, str) for key in payload_value)
        ):
            self._send_response(
                APIResponse(
                    False,
                    data={"state": "broker_dispatch_denied", "code": "invalid_dispatch"},
                    error="Dispatch requires exact contract, operation, and object payload",
                ),
                400,
            )
            return
        payload: dict[str, object] = {
            key: value for key, value in payload_value.items() if isinstance(key, str)
        }
        payload["_session_id"] = session_id_value
        try:
            result = session.invoke(
                contract_value.strip(),
                operation_value.strip(),
                payload,
            )
        except (HostCoreError, KeyError, RuntimeError, ValueError) as error:
            code = getattr(error, "code", "invalid_dispatch")
            self._send_response(
                APIResponse(
                    False,
                    data={
                        "state": "broker_dispatch_denied",
                        "code": str(code),
                    },
                    error=str(error),
                ),
                409,
            )
            return
        self._send_response(APIResponse(True, data=dict(result)))

    def _serve_panel_bootstrap_page(self) -> None:
        document = b"""<!doctype html><meta charset=\"utf-8\"><title>Tobkiri</title>
<script>
const code=new URL(location.href).searchParams.get('code');
if(!code){document.body.textContent='Tobkiri Launcher authentication required';}
else fetch('/api/panel/auth/exchange',{method:'POST',credentials:'same-origin',
headers:{'Content-Type':'application/json'},body:JSON.stringify({code})})
.then(r=>{if(!r.ok)throw new Error('authentication failed');return r.json()})
.then(v=>{sessionStorage.setItem('rumi-panel-csrf',v.data.csrf_token);location.replace('/panel/')})
.catch(()=>{document.body.textContent='Tobkiri Launcher authentication failed';});
</script>"""
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(document)))
            self.end_headers()
            self.wfile.write(document)
        except self._CLIENT_DISCONNECT_EXCEPTIONS:
            self.close_connection = True

    def do_OPTIONS(self) -> None:
        """Answer local panel preflight without widening the origin set."""

        self._reset_request_state()
        origin = self._get_cors_origin(self.headers.get("Origin", ""))
        if not origin:
            self._send_response(APIResponse(False, error="Forbidden origin"), 403)
            return
        try:
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header(
                "Access-Control-Allow-Headers",
                "Content-Type, X-Rumi-CSRF, X-Rumi-Desktop-Bootstrap",
            )
            self.send_header("Content-Length", "0")
            self.end_headers()
        except self._CLIENT_DISCONNECT_EXCEPTIONS:
            self.close_connection = True

    def do_GET(self) -> None:
        """Dispatch the finite read-only route set."""

        self._reset_request_state()
        path = urlparse(self.path).path
        if path == "/health":
            self._handle_health()
            return
        if path == "/":
            self.send_response(302)
            self.send_header("Location", "/panel/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path == "/api/setup/status":
            self._handle_setup_status()
            return
        if path == "/api/setup/packs":
            if not self._setup_pre_auth_allowed() and not self._check_auth("GET", path):
                self._send_response(APIResponse(False, error="Unauthorized"), 401)
                return
            self._send_mapping_result(self._setup_list_packs())
            return
        if path == "/api/setup/migration/status":
            self._send_mapping_result(self._setup_get_migration_status())
            return
        mount = self._match_web_mount(path)
        if mount is not None:
            if mount["auth_required"] and not self._check_auth("GET", path):
                if mount["path_prefix"] == "/panel" and path in {
                    "/panel",
                    "/panel/",
                    "/panel/index.html",
                }:
                    self._serve_panel_bootstrap_page()
                else:
                    self._send_response(APIResponse(False, error="Unauthorized"), 401)
                return
            self._serve_static_file(path, mount)
            return
        if self._retired_api_path(path):
            self._send_retired_api(path)
            return
        self._send_not_found()

    def do_POST(self) -> None:
        """Dispatch canonical setup/auth and exact Broker operations."""

        self._reset_request_state()
        path = urlparse(self.path).path
        if path == "/api/setup/complete":
            self._discard_request_body()
            self._send_mapping_result(self._retired_setup_complete_state())
            return
        if path == "/api/panel/auth/bootstrap":
            self._handle_panel_bootstrap()
            return
        if path == "/api/panel/auth/exchange":
            body = self._parse_object_body()
            if body is not None:
                self._handle_panel_exchange(body)
            return
        if path == "/api/setup/packs/install":
            if not self._setup_pre_auth_allowed() and not self._check_auth("POST", path):
                self._discard_request_body()
                self._send_response(APIResponse(False, error="Unauthorized"), 401)
                return
            body = self._parse_object_body()
            if body is not None:
                self._send_mapping_result(self._setup_install_pack(body))
            return
        if path == "/api/v4/dispatch":
            if not self._check_auth("POST", path):
                self._discard_request_body()
                self._send_response(APIResponse(False, error="Unauthorized"), 401)
                return
            body = self._parse_object_body()
            if body is not None:
                self._handle_v4_dispatch(body)
            return
        if self._retired_api_path(path):
            self._discard_request_body()
            self._send_retired_api(path)
            return
        self._discard_request_body()
        self._send_not_found()

    def do_PUT(self) -> None:
        """Retire historical mutation routes without parsing their payloads."""

        self._reset_request_state()
        path = urlparse(self.path).path
        self._discard_request_body()
        if self._retired_api_path(path):
            self._send_retired_api(path)
        else:
            self._send_not_found()

    def do_DELETE(self) -> None:
        """Retire historical deletion routes without manager access."""

        self.do_PUT()

    def do_PATCH(self) -> None:
        """Retire historical partial mutations without manager access."""

        self.do_PUT()


class PackAPIServer:
    """Own one verified loopback HTTP server and captured v4 handler."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        *,
        panel_auth_manager: PanelAuthManager | None = None,
        dispatch_session: DispatchSession | None = None,
        app_lifecycle_manager: LifecyclePort | None = None,
    ) -> None:
        self.config = RuntimeHTTPConfig.verify(host, port)
        self.host = self.config.host
        self.port = self.config.port
        self._panel_auth_manager = panel_auth_manager or get_panel_auth_manager()
        self._dispatch_session = dispatch_session
        self.app_lifecycle_manager = app_lifecycle_manager
        self.server: _PackThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None
        self.handler_class: type[PackAPIHandler] | None = None
        self._lifecycle_lock = threading.RLock()

    def start(self) -> None:
        """Start a fresh finite handler with no inherited route state."""

        with self._lifecycle_lock:
            if self.is_running():
                return
            handler = PackAPIHandler.canonical_v4_server_handler(
                panel_auth_manager=self._panel_auth_manager,
                dispatch_session=self._dispatch_session,
                app_lifecycle_manager=self.app_lifecycle_manager,
            )
            server = _PackThreadingHTTPServer((self.host, self.port), handler)
            actual_port = int(server.server_address[1])
            handler._runtime_port = actual_port
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            self.port = actual_port
            self.handler_class = handler
            self.server = server
            self.thread = thread
            thread.start()
        logger.info("Pack v4 API server started on http://%s:%s", self.host, self.port)

    def stop(self) -> None:
        """Stop the server and discard its captured handler bindings."""

        with self._lifecycle_lock:
            server = self.server
            thread = self.thread
            if server is not None:
                server.shutdown()
                server.server_close()
                self.server = None
            if thread is not None:
                thread.join(timeout=THREAD_JOIN_TIMEOUT_SECONDS)
                self.thread = None
            self.handler_class = None
        logger.info("Pack v4 API server stopped")

    def is_running(self) -> bool:
        """Return whether the serving thread is alive."""

        return (
            self.server is not None
            and self.thread is not None
            and self.thread.is_alive()
        )


_api_server: PackAPIServer | None = None


def get_pack_api_server() -> PackAPIServer | None:
    """Return the process-local Pack v4 HTTP server, if started."""

    return _api_server


def initialize_pack_api_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    *,
    panel_auth_manager: PanelAuthManager | None = None,
    dispatch_session: DispatchSession | None = None,
    app_lifecycle_manager: LifecyclePort | None = None,
) -> PackAPIServer:
    """Replace the process-local server with one verified v4 instance."""

    global _api_server
    if _api_server is not None:
        _api_server.stop()
    server = PackAPIServer(
        host=host,
        port=port,
        panel_auth_manager=panel_auth_manager,
        dispatch_session=dispatch_session,
        app_lifecycle_manager=app_lifecycle_manager,
    )
    server.start()
    _api_server = server
    return server


def shutdown_pack_api_server() -> None:
    """Stop and forget the process-local Pack v4 HTTP server."""

    global _api_server
    if _api_server is not None:
        _api_server.stop()
        _api_server = None


__all__ = [
    "PackAPIHandler",
    "PackAPIServer",
    "RuntimeHTTPConfig",
    "get_pack_api_server",
    "initialize_pack_api_server",
    "shutdown_pack_api_server",
]
