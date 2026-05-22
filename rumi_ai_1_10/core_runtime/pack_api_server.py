"""
pack_api_server.py - Pack管理HTTP APIサーバー

Pack承認、コンテナ操作、特権操作、Capability Handler候補管理、
pip依存ライブラリ管理のHTTP APIを提供。
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import base64
import re
import secrets
import threading
import time
import collections
from pathlib import Path
from typing import Any, Optional
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

from .hmac_key_manager import get_hmac_key_manager, HMACKeyManager
from .panel_auth import get_panel_auth_manager, PanelAuthManager
from .runtime_port import resolve_runtime_port

from .validation import (
    validate_pack_id as _v_validate_pack_id,
    is_safe_id as _v_is_safe_id,
    PACK_ID_RE,
    SAFE_ID_RE,
    MAX_REQUEST_BODY_BYTES,
    HANDLER_NAME_RE,
)

from .api.route_handlers import _compile_template_path, _is_safe_path_param

from .api.api_response import APIResponse

from .api import (
    PackHandlersMixin,
    ContainerHandlersMixin,
    NetworkHandlersMixin,
    CapabilityGrantHandlersMixin,
    StoreShareHandlersMixin,
    PrivilegeHandlersMixin,
    CapabilityInstallerHandlersMixin,
    PipHandlersMixin,
    SecretsHandlersMixin,
    StoreHandlersMixin,
    UnitHandlersMixin,
    FlowHandlersMixin,
    RouteHandlersMixin,
    PackLifecycleHandlersMixin,
    ControlPanelHandlersMixin,
    CapabilityGraphHandlersMixin,
    SetupHandlersMixin,
    OAuthHandlersMixin,
    ViewerHandlersMixin,
    DesktopHandlersMixin,
)
from .api._helpers import _log_internal_error, _SAFE_ERROR_MSG


logger = logging.getLogger(__name__)


# --- スレッド終了待ちタイムアウト (秒) --- (PACK_ID_RE, SAFE_ID_RE, MAX_REQUEST_BODY_BYTES は validation.py から import)
THREAD_JOIN_TIMEOUT_SECONDS = 5

# --- W20-D: IP-based sliding window rate limiter ---
class _RateLimiter:
    """IP アドレスベースのスライディングウィンドウレートリミッター。

    メモリ上の dict で管理し、外部依存なし。threading.Lock でスレッドセーフ。
    """

    def __init__(
        self,
        max_requests: int = 120,
        window_seconds: float = 60.0,
        max_ips: int = 10000,
    ) -> None:
        self._max_requests = max_requests
        self._window = float(window_seconds)
        self._max_ips = max_ips
        self._lock = threading.Lock()
        # ip -> deque of monotonic timestamps
        self._requests: dict[str, collections.deque] = {}

    # -- public API --

    def is_allowed(self, ip: str) -> bool:
        """ip からのリクエストが許可されるなら True を返す。"""
        now = time.monotonic()
        with self._lock:
            return self._is_allowed_locked(ip, now)

    # -- internal --

    def _is_allowed_locked(self, ip: str, now: float) -> bool:
        # 既存エントリのクリーンアップ
        if ip in self._requests:
            dq = self._requests[ip]
            cutoff = now - self._window
            while dq and dq[0] <= cutoff:
                dq.popleft()
            if not dq:
                del self._requests[ip]

        # 新規 IP のスロット確保
        if ip not in self._requests:
            if len(self._requests) >= self._max_ips:
                self._evict_oldest()
            self._requests[ip] = collections.deque()

        dq = self._requests[ip]
        if len(dq) >= self._max_requests:
            return False
        dq.append(now)
        return True

    def _evict_oldest(self) -> None:
        """最もリクエストが古い IP を 1 件除去する。"""
        oldest_ip = None
        oldest_time = float("inf")
        for ip, dq in self._requests.items():
            if not dq:
                oldest_ip = ip
                break
            if dq[0] < oldest_time:
                oldest_time = dq[0]
                oldest_ip = ip
        if oldest_ip is not None:
            del self._requests[oldest_ip]


_rate_limiter = _RateLimiter(
    max_requests=int(os.environ.get("RUMI_API_RATE_LIMIT", "120")),
    window_seconds=float(os.environ.get("RUMI_API_RATE_WINDOW", "60")),
)


class _PackThreadingHTTPServer(ThreadingHTTPServer):
    """Thread-per-request server so long SSE streams do not block control APIs."""

    allow_reuse_address = True
    daemon_threads = True
    block_on_close = False
    request_queue_size = int(os.environ.get("RUMI_API_REQUEST_QUEUE_SIZE", "128"))


# _SAFE_ERROR_MSG: moved to api._helpers


# _log_internal_error: moved to api._helpers


class PackAPIHandler(
    PackHandlersMixin,
    ContainerHandlersMixin,
    NetworkHandlersMixin,
    CapabilityGrantHandlersMixin,
    StoreShareHandlersMixin,
    PrivilegeHandlersMixin,
    CapabilityInstallerHandlersMixin,
    PipHandlersMixin,
    SecretsHandlersMixin,
    StoreHandlersMixin,
    UnitHandlersMixin,
    FlowHandlersMixin,
    RouteHandlersMixin,
    PackLifecycleHandlersMixin,
    ControlPanelHandlersMixin,
    CapabilityGraphHandlersMixin,
    SetupHandlersMixin,
    OAuthHandlersMixin,
    ViewerHandlersMixin,
    DesktopHandlersMixin,
    BaseHTTPRequestHandler,
):
    approval_manager = None
    container_orchestrator = None
    host_privilege_manager = None
    internal_token: str = ""
    _allowed_origins: Optional[list[str]] = None
    _allowed_origins_from_env: bool = False
    _allowed_origins_cache_key: Optional[tuple[str, str]] = None
    _hmac_key_manager: Optional[HMACKeyManager] = None
    _panel_auth_manager: Optional[PanelAuthManager] = None
    kernel = None  # Kernel インスタンス参照（Flow実行API用）
    app_lifecycle_manager = None  # AppLifecycleManager インスタンス参照（Phase A）
    _request_auth_mode: Optional[str] = None
    _panel_session: Optional[dict[str, Any]] = None
    _panel_session_cookie: Optional[str] = None
    _web_mounts: list[dict[str, Any]] = []           # web_mount テーブル（テーブル駆動静的配信）
    _pre_auth_table: list[dict[str, Any]] = []       # pre_auth_routes テーブル（テーブル駆動認証バイパス）
    _api_route_exact: dict[tuple[str, str], dict[str, Any]] = {}      # api_routes 完全一致テーブル {(METHOD, path): entry}
    _api_route_patterns: list[tuple[Any, Any, Any, dict[str, Any]]] = []   # api_routes パターンテーブル [(METHOD, regex, params, entry)]
    
    def log_message(self, format: str, *args) -> None:
        sanitized_args = tuple(self._redact_log_value(arg) for arg in args)
        try:
            message = format % sanitized_args if sanitized_args else format
        except Exception:
            message = " ".join(sanitized_args) if sanitized_args else format
        logger.info("API: %s", message)

    @staticmethod
    def _redact_log_value(value: object) -> str:
        text = "" if value is None else str(value)
        return re.sub(
            r"([?&](?:token|code)=)[^&\s\"]+",
            r"\1[REDACTED]",
            text,
            flags=re.IGNORECASE,
        )

    @staticmethod
    def _validate_pack_id(pack_id: str) -> bool:
        """pack_id が安全なパターンに合致するか検証する (Fix #9)"""
        return _v_validate_pack_id(pack_id)

    @staticmethod
    def _is_safe_id(value: str) -> bool:
        """汎用 ID バリデーション。staging_id, privilege_id, flow_id 等に使用する。"""
        return _v_is_safe_id(value)


    # --- テーブル駆動: web_mount / pre_auth_routes ---

    @classmethod
    def load_web_mounts(cls, registry, pack_ids: Optional[set[str]] = None) -> int:
        """Registry から全 Pack の web_mount 情報を読み込み、テーブルを構築する。"""
        cls._web_mounts = []
        if registry is None:
            return 0
        count = 0
        for pack_id, pack_info in registry.packs.items():
            if pack_ids is not None and pack_id not in pack_ids:
                continue
            wm = pack_info.ecosystem.get("web_mount")
            if not wm or not isinstance(wm, dict):
                continue
            path_prefix = wm.get("path_prefix", "")
            static_root_rel = wm.get("static_root", "")
            if not path_prefix or not static_root_rel:
                continue
            # subdir が利用可能ならそちらを使う（ecosystem.json の位置基準）
            base_dir = getattr(pack_info, "subdir", None) or pack_info.path
            web_root = Path(str(base_dir)) / static_root_rel
            cls._web_mounts.append({
                "path_prefix": path_prefix,
                "web_root": web_root.resolve(),
                "spa_fallback": wm.get("spa_fallback", False),
                "auth_required": wm.get("auth_required", True),
                "pack_id": pack_id,
            })
            count += 1
        # 最長一致のために path_prefix の長さで降順ソート
        cls._web_mounts.sort(key=lambda e: len(e["path_prefix"]), reverse=True)
        logger.info("Loaded %d web_mount entries", count)
        return count

    @classmethod
    def load_pre_auth_routes(cls, registry, pack_ids: Optional[set[str]] = None) -> int:
        """Registry から全 Pack の pre_auth_routes を読み込み、テーブルを構築する。

        web_mount で auth_required=false の静的配信パスも自動的に
        pre-auth テーブルに含める。
        """
        cls._pre_auth_table = []
        if registry is None:
            return 0
        count = 0
        for pack_id, pack_info in registry.packs.items():
            if pack_ids is not None and pack_id not in pack_ids:
                continue
            # 1. 明示的な pre_auth_routes
            routes = pack_info.ecosystem.get("pre_auth_routes")
            if routes and isinstance(routes, list):
                for route in routes:
                    if not isinstance(route, dict):
                        continue
                    method = route.get("method", "").upper()
                    if not method:
                        continue
                    entry = {"method": method, "pack_id": pack_id}
                    if "path" in route:
                        entry["path"] = route["path"]
                    if "path_prefix" in route:
                        entry["path_prefix"] = route["path_prefix"]
                    cls._pre_auth_table.append(entry)
                    count += 1
            # 2. web_mount で auth_required=false のパスも pre-auth に追加
            wm = pack_info.ecosystem.get("web_mount")
            if wm and isinstance(wm, dict) and not wm.get("auth_required", True):
                prefix = wm.get("path_prefix", "")
                if prefix:
                    for m in ("GET", "POST", "PUT", "DELETE"):
                        cls._pre_auth_table.append({
                            "method": m,
                            "path_prefix": prefix,
                            "pack_id": pack_id,
                            "_source": "web_mount",
                        })
                    count += 4
        logger.info("Loaded %d pre_auth_route entries", count)
        return count

    def _match_web_mount(self, request_path: str):
        """リクエストパスが web_mount テーブルにマッチするか判定する。

        最長一致（テーブルは path_prefix 長の降順ソート済み）。
        マッチした場合は web_mount dict を返す。しなければ None。
        """
        for wm in self._web_mounts:
            prefix = wm["path_prefix"]
            if request_path == prefix or request_path.startswith(prefix + "/"):
                return wm
        fallback_mounts = {
            "/panel": {
                "web_root": Path(__file__).resolve().parent / "core_pack" / "core_control_panel" / "web",
                "spa_fallback": True,
                "index_file": "index.html",
                "auth_required": True,
                "pack_id": "core_control_panel",
            },
            "/setup": {
                "web_root": Path(__file__).resolve().parent / "core_pack" / "core_setup" / "web",
                "spa_fallback": True,
                "index_file": "index.html",
                "auth_required": False,
                "pack_id": "core_setup",
            },
        }
        for prefix, mount in fallback_mounts.items():
            if request_path == prefix or request_path.startswith(prefix + "/"):
                return {"path_prefix": prefix, **mount}
        return None


    @classmethod
    def load_api_routes(cls, registry) -> int:
        """Registry から全 Pack の api_routes を読み込み、ルーティングテーブルを構築する。

        完全一致ルートは dict で O(1) ルックアップ。
        パスパラメータ付きルートは正規表現でマッチ（route_handlers.py のパターンを踏襲）。
        """
        cls._api_route_exact = {}
        cls._api_route_patterns = []
        if registry is None:
            return 0
        count = 0
        for pack_id, pack_info in registry.packs.items():
            routes = pack_info.ecosystem.get("api_routes")
            if not routes or not isinstance(routes, list):
                continue
            for route in routes:
                if not isinstance(route, dict):
                    continue
                method = route.get("method", "").upper()
                handler_name = route.get("handler", "")
                function_id = route.get("function_id", route.get("function", ""))
                if not method or not (handler_name or function_id):
                    continue
                if handler_name and not HANDLER_NAME_RE.match(handler_name):
                    logger.warning("Invalid handler name in api_routes: %s", handler_name)
                    continue
                entry = {
                    "handler": handler_name,
                    "function_id": function_id,
                    "pack_id": pack_id,
                    "pass_body": route.get("pass_body", False),
                    "response_mode": route.get("response_mode", "result"),
                    "args": dict(route.get("args") or {}),
                    "path_param_map": dict(route.get("path_param_map") or {}),
                }
                if "path_pattern" in route:
                    compiled = _compile_template_path(route["path_pattern"])
                    if compiled is not None:
                        pattern, param_names = compiled
                        cls._api_route_patterns.append(
                            (method, pattern, param_names, entry)
                        )
                        count += 1
                elif "path" in route:
                    cls._api_route_exact[(method, route["path"])] = entry
                    count += 1
        logger.info("Loaded %d api_route entries", count)
        return count

    def _is_pre_auth_route(self, method: str, path: str) -> bool:
        """method + path が pre_auth_table にマッチするか判定する。"""
        method_upper = method.upper()
        core_pre_auth_routes = {
            ("POST", "/api/panel/auth/bootstrap"),
            ("POST", "/api/panel/auth/exchange"),
            ("GET", "/api/setup/status"),
            ("GET", "/api/setup/oauth/start"),
            ("GET", "/callback"),
            ("POST", "/api/setup/complete"),
        }
        if (method_upper, path) in core_pre_auth_routes:
            return True
        # Provider webhooks must reach their own signature/shared-secret checks
        # before panel or bearer auth can apply.
        if method_upper == "POST":
            if path in {
                "/api/integrations/line/webhook",
                "/api/integrations/slack/events",
                "/api/integrations/discord/interactions",
                "/api/integrations/discord/events",
            }:
                return True
            if path.startswith("/api/webhooks/inbound/"):
                return True
        for entry in self._pre_auth_table:
            if entry["method"] != method_upper:
                continue
            if "path" in entry and entry["path"] == path:
                return True
            if "path_prefix" in entry and path.startswith(entry["path_prefix"]):
                return True
        return False


    def _dispatch_api_route(
        self,
        method: str,
        path: str,
        body: Optional[dict[str, Any]] = None,
    ) -> bool:
        """api_routes テーブルからルートをディスパッチする。

        マッチした場合はレスポンスを送信して True を返す。
        マッチしなかった場合は False を返す（既存分岐に fallthrough）。
        """
        method_upper = method.upper()

        # 1. 完全一致 (O(1))
        entry = self._api_route_exact.get((method_upper, path))
        path_params = {}

        # 2. パターンマッチ (正規表現)
        if entry is None:
            normalized = path.rstrip("/")
            if not normalized.startswith("/"):
                normalized = "/" + normalized
            for tmpl_method, pattern, param_names, route_entry in self._api_route_patterns:
                if tmpl_method != method_upper:
                    continue
                m = pattern.match(normalized)
                if m is None:
                    continue
                safe = True
                params = {}
                for name in param_names:
                    decoded = unquote(m.group(name))
                    if not _is_safe_path_param(decoded):
                        safe = False
                        break
                    params[name] = decoded
                if safe:
                    entry = route_entry
                    path_params = params
                    break

        if entry is None:
            return False

        handler_name = entry["handler"]
        pass_body = entry.get("pass_body", False)
        response_mode = entry.get("response_mode", "result")

        # パスパラメータのバリデーション
        for param_val in path_params.values():
            if not self._is_safe_id(param_val):
                self._send_response(
                    APIResponse(False, error="Invalid path parameter"), 400
                )
                return True

        # ハンドラ呼び出し
        try:
            if entry.get("function_id"):
                from .pack_function_runtime import invoke_pack_function

                call_args = dict(body if pass_body and body is not None else {})
                # Route-level args define the contract for fixed endpoints such as
                # /approve and /reject, so body values must not override them.
                call_args.update(entry.get("args") or {})
                param_map = entry.get("path_param_map") or {}
                if param_map:
                    for target_key, source_key in param_map.items():
                        if source_key in path_params:
                            call_args[target_key] = path_params[source_key]
                else:
                    call_args.update(path_params)
                result = invoke_pack_function(
                    entry["pack_id"],
                    entry["function_id"],
                    call_args,
                    {"pack_id": entry["pack_id"], "method": method_upper, "path": path},
                )
            else:
                # ハンドラの存在確認
                handler = getattr(self, handler_name, None)
                if handler is None:
                    logger.error("api_route handler not found: %s", handler_name)
                    self._send_response(APIResponse(False, error=_SAFE_ERROR_MSG), 500)
                    return True

                args: list[Any] = []
                if path_params:
                    args.extend(path_params.values())
                if pass_body:
                    args.append(body if body is not None else {})

                result = handler(*args)

            sse_events = self._sse_events_from_result(result)
            if sse_events is not None:
                self._send_sse(sse_events)
            elif response_mode == "raw":
                self._send_response(APIResponse(True, data=result))
            else:
                self._send_result(result)
        except Exception as e:
            _log_internal_error(f"api_route:{handler_name}", e)
            self._send_response(APIResponse(False, error=_SAFE_ERROR_MSG), 500)

        return True

    def _send_response(
        self,
        response: APIResponse,
        status: int = 200,
        extra_headers: Optional[list[tuple[str, str]]] = None,
    ) -> None:
        data = response.to_json().encode('utf-8')
        response_headers = list(extra_headers or [])
        if self._panel_session_cookie:
            response_headers.append(("Set-Cookie", self._panel_session_cookie))
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        origin = self._get_cors_origin(self.headers.get('Origin', ''))
        if origin:
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
        for header_name, header_value in response_headers:
            self.send_header(header_name, header_value)
        self.end_headers()
        self.wfile.write(data)

    def _send_sse(self, events) -> None:
        response_headers: list[tuple[str, str]] = []
        if self._panel_session_cookie:
            response_headers.append(("Set-Cookie", self._panel_session_cookie))
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache, no-transform')
        self.send_header('Connection', 'close')
        origin = self._get_cors_origin(self.headers.get('Origin', ''))
        if origin:
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
        for header_name, header_value in response_headers:
            self.send_header(header_name, header_value)
        self.end_headers()
        try:
            for event in events:
                if isinstance(event, bytes):
                    payload = event
                else:
                    payload = (
                        "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
                    ).encode('utf-8')
                self.wfile.write(payload)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            self.close_connection = True

    @staticmethod
    def _sse_events_from_result(result):
        if isinstance(result, dict) and result.get("_sse"):
            return result.get("events", [])
        if (
            isinstance(result, dict)
            and result.get("status") == "ok"
            and isinstance(result.get("data"), dict)
            and result["data"].get("_sse")
        ):
            return result["data"].get("events", [])
        return None

    def _discard_request_body(self) -> None:
        """Consume unread request bytes before returning an early response."""
        try:
            raw_cl = self.headers.get('Content-Length', '0')
            content_length = int(raw_cl)
        except (TypeError, ValueError):
            content_length = 0
        if content_length <= 0:
            return
        try:
            self.rfile.read(content_length)
        except Exception:
            logger.debug("Failed to discard request body", exc_info=True)

    def _send_result(self, result, error_status: int = 500) -> None:
        """ハンドラ戻り値を判定してレスポンスを送信する (T-008)。

        戻り値が dict で ``"error"`` キーを含む場合はエラーレスポンスとして送信し、
        それ以外は成功レスポンスとして送信する。

        handler が ``status_code`` キーを返した場合、その値を HTTP ステータスに使用する。
        ``status_code`` が無い場合は *error_status* をデフォルトとする。
        """
        sse_events = self._sse_events_from_result(result)
        if sse_events is not None:
            self._send_sse(sse_events)
            return
        if isinstance(result, dict) and "error" in result:
            status = result.get("status_code", error_status)
            self._send_response(
                APIResponse(False, error=result["error"]), status
            )
        else:
            self._send_response(APIResponse(True, data=result))
    
    @staticmethod
    def _is_loopback_ip(ip: str) -> bool:
        return ip in {"127.0.0.1", "::1", "::ffff:127.0.0.1", "localhost"}

    def _check_rate_limit(self, path: str) -> bool:
        """レート制限チェック。制限超過なら 429 を返して False。"""
        ip = self.client_address[0]
        if self._is_loopback_ip(ip) and (path.startswith("/api/panel/") or path.startswith("/panel") or path.startswith("/api/setup/")):
            return True
        if not _rate_limiter.is_allowed(ip):
            self.send_error(429, "Too Many Requests")
            return False
        return True

    def _check_bearer_auth(self) -> bool:
        auth_header = self.headers.get('Authorization', '')

        if not auth_header:
            return False

        # Bearer プレフィックスを除去
        if not auth_header.startswith("Bearer "):
            return False
        token = auth_header[7:]  # len("Bearer ") == 7

        # 1. HMACKeyManager 経由で検証（ローテーション対応）
        if self._hmac_key_manager is not None:
            return self._hmac_key_manager.verify_token(token)

        # 2. フォールバック: 従来の internal_token での検証（後方互換）
        if not self.internal_token:
            logger.error("API token not configured - rejecting request")
            return False

        return hmac.compare_digest(token, self.internal_token)

    def _parse_cookie_header(self) -> dict[str, str]:
        raw_cookie = self.headers.get("Cookie", "")
        if not raw_cookie:
            return {}
        jar = cookies.SimpleCookie()
        try:
            jar.load(raw_cookie)
        except cookies.CookieError:
            return {}
        return {key: morsel.value for key, morsel in jar.items()}

    @staticmethod
    def _build_set_cookie(
        name: str,
        value: str,
        *,
        path: str,
        max_age: int,
        http_only: bool,
        same_site: str = "Strict",
    ) -> str:
        jar = cookies.SimpleCookie()
        jar[name] = value
        morsel = jar[name]
        morsel["path"] = path
        morsel["max-age"] = str(max_age)
        morsel["samesite"] = same_site
        if http_only:
            morsel["httponly"] = True
        return morsel.OutputString()

    def _check_panel_origin(self) -> bool:
        origin = self.headers.get("Origin", "")
        return bool(self._get_cors_origin(origin))

    def _check_panel_session(self, method: str) -> bool:
        if self._panel_auth_manager is None:
            return False
        cookies_map = self._parse_cookie_header()
        session_id = cookies_map.get("rumi_panel_session", "")
        session = self._panel_auth_manager.verify_session(session_id)
        if session is None:
            return False

        if method.upper() in {"POST", "PUT", "DELETE"}:
            if not self._check_panel_origin():
                return False
            csrf_header = self.headers.get("X-Rumi-CSRF", "")
            session_csrf = session.get("csrf_token", "")
            if not csrf_header or not hmac.compare_digest(csrf_header, session_csrf):
                return False

        self._panel_session = session
        self._panel_session_cookie = self._build_set_cookie(
            "rumi_panel_session",
            session_id,
            path="/",
            max_age=int(session.get("expires_in", PanelAuthManager.DEFAULT_SESSION_TTL_SECONDS)),
            http_only=True,
        )
        return True

    def _check_auth(self, method: str, path: str) -> bool:
        if self._check_bearer_auth():
            self._request_auth_mode = "bearer"
            return True

        if path.startswith("/api/") and self._check_panel_session(method):
            self._request_auth_mode = "panel_session"
            return True

        self._request_auth_mode = None
        return False

    def _check_web_mount_auth(self, method: str, web_mount: dict[str, Any]) -> bool:
        if self._check_bearer_auth():
            self._request_auth_mode = "bearer"
            return True

        if self._check_panel_session(method):
            self._request_auth_mode = "panel_session"
            return True

        self._request_auth_mode = None
        return False

    @staticmethod
    def _allows_public_bootstrap_page(request_path: str, web_mount: dict[str, Any]) -> bool:
        if web_mount.get("pack_id") != "core_control_panel":
            return False
        prefix = web_mount.get("path_prefix", "")
        if not prefix:
            return False
        return request_path in {prefix, f"{prefix}/", f"{prefix}/index.html"}

    def _serve_panel_bootstrap_page(self) -> None:
        html = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Rumi AI</title>
    <style>
      :root { color-scheme: dark; }
      body {
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        background: #0f172a;
        color: #e2e8f0;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }
      main {
        width: min(32rem, calc(100vw - 2rem));
        padding: 2rem;
        border-radius: 1rem;
        background: rgba(15, 23, 42, 0.92);
        box-shadow: 0 20px 45px rgba(15, 23, 42, 0.35);
      }
      h1 {
        margin: 0 0 0.75rem;
        font-size: 1.25rem;
      }
      p {
        margin: 0;
        line-height: 1.5;
        color: #cbd5e1;
      }
      .error {
        color: #fca5a5;
      }
    </style>
  </head>
  <body>
    <main>
      <h1 id="title">Starting Rumi AI…</h1>
      <p id="message">Exchanging your one-time desktop login code.</p>
    </main>
    <script>
      (async () => {
        const title = document.getElementById('title');
        const message = document.getElementById('message');
        const PANEL_CSRF_STORAGE_KEY = 'rumi-panel-csrf';
        const url = new URL(window.location.href);
        const code = url.searchParams.get('code');

        const fail = (text) => {
          title.textContent = 'Panel sign-in failed';
          message.textContent = text;
          message.classList.add('error');
        };

        if (!code) {
          fail('This panel launch is missing a valid one-time login code.');
          return;
        }

        try {
          const response = await fetch('/api/panel/auth/exchange', {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code }),
          });

          const envelope = await response.json().catch(() => ({}));
          if (!response.ok || !envelope.success || !envelope.data || !envelope.data.csrf_token) {
            throw new Error(envelope.error || `Panel bootstrap failed: ${response.status}`);
          }

          sessionStorage.setItem(PANEL_CSRF_STORAGE_KEY, envelope.data.csrf_token);
          url.searchParams.delete('code');
          window.location.replace(url.pathname + url.search + url.hash);
        } catch (error) {
          fail(error instanceof Error ? error.message : 'Panel bootstrap failed.');
        }
      })();
    </script>
  </body>
</html>
"""
        data = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        origin = self._get_cors_origin(self.headers.get("Origin", ""))
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.end_headers()
        self.wfile.write(data)

    def _handle_panel_bootstrap(self) -> None:
        if self._panel_auth_manager is None:
            self._send_response(APIResponse(False, error="Panel auth unavailable"), 503)
            return

        bootstrap_secret = self.headers.get("X-Rumi-Desktop-Bootstrap", "")
        if not self._panel_auth_manager.validate_bootstrap_secret(bootstrap_secret):
            self._send_response(APIResponse(False, error="Unauthorized"), 401)
            return

        payload = self._panel_auth_manager.issue_login_code()
        self._send_response(APIResponse(True, data=payload))

    def _handle_panel_exchange(self, body: dict[str, Any]) -> None:
        if self._panel_auth_manager is None:
            self._send_response(APIResponse(False, error="Panel auth unavailable"), 503)
            return
        if not self._check_panel_origin():
            self._send_response(APIResponse(False, error="Forbidden origin"), 403)
            return

        code = str(body.get("code", "")).strip()
        exchange = self._panel_auth_manager.exchange_code(code)
        if exchange is None:
            self._send_response(APIResponse(False, error="Invalid or expired code"), 401)
            return

        session_cookie = self._build_set_cookie(
            "rumi_panel_session",
            exchange["session_id"],
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
            extra_headers=[("Set-Cookie", session_cookie)],
        )
    
    def _read_raw_body(self) -> Optional[bytes]:
        """リクエストボディを読み取り、インスタンスに保持して返す。

        サイズ超過時は 413 レスポンスを送信し None を返す。
        Content-Length が不正な場合は 400 レスポンスを送信し None を返す。

        Returns:
            bytes: 読み取ったボディ。
            None: サイズ超過 / ヘッダー不正（レスポンス送信済み）。
        """
        raw_cl = self.headers.get('Content-Length', '0')
        try:
            content_length = int(raw_cl)
        except (ValueError, TypeError):
            self._send_response(
                APIResponse(False, error="Invalid Content-Length header"), 400
            )
            return None
        if content_length < 0:
            self._send_response(
                APIResponse(False, error="Invalid Content-Length header"), 400
            )
            return None
        if content_length == 0:
            self._raw_body_bytes = b""
            return b""
        if content_length > MAX_REQUEST_BODY_BYTES:
            self._send_response(
                APIResponse(False, error="Request body too large"), 413
            )
            return None
        raw = self.rfile.read(content_length)
        self._raw_body_bytes = raw
        return raw

    def _parse_body(self) -> Optional[dict]:
        """リクエストボディをJSONとしてパースする。

        Returns:
            dict: パース結果。空ボディは {} を返す。
            None: サイズ超過 / パース失敗（レスポンス送信済み）。
        """
        raw = self._read_raw_body()
        if raw is None:
            return None  # _read_raw_body がエラーレスポンスを送信済み
        if not raw:
            return {}
        try:
            return json.loads(raw.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send_response(
                APIResponse(False, error="Invalid JSON in request body"), 400
            )
            return None
    

    # --- Phase A: 静的ファイル配信メソッド ---
    _MIME_TYPES = {
        ".html": "text/html; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".svg": "image/svg+xml",
        ".ico": "image/x-icon",
        ".woff": "font/woff",
        ".woff2": "font/woff2",
        ".ttf": "font/ttf",
        ".map": "application/json",
    }

    def _serve_static_file(
        self,
        request_path: str,
        _wm: Optional[dict[str, Any]] = None,
    ) -> None:
        """Pack が提供する Web UI の静的ファイルを配信する（認証不要）。

        パストラバーサル防止: Path.resolve() + relative_to() で web_root 内に制限。
        テーブル駆動: _web_mounts テーブルからパスを解決する。
        """
        if _wm is None:
            _wm = self._match_web_mount(request_path)
        if _wm is None:
            self._send_response(APIResponse(False, error="Not found"), 404)
            return

        path_prefix = _wm["path_prefix"]
        web_root = _wm["web_root"]
        spa_fallback = _wm.get("spa_fallback", False)
        index_file = _wm.get("index_file", "index.html")

        sub_path = request_path[len(path_prefix):]
        if not sub_path or sub_path == "/":
            sub_path = "/" + index_file

        # パストラバーサル防止
        try:
            target = (web_root / sub_path.lstrip("/")).resolve()
            target.relative_to(web_root.resolve())
        except (ValueError, OSError):
            self._send_response(APIResponse(False, error="Forbidden"), 403)
            return

        if not target.is_file():
            # SPA フォールバック: 拡張子のないパスは index.html に解決
            index_fallback = web_root / index_file
            if spa_fallback and index_fallback.is_file() and "." not in target.name:
                target = index_fallback
            else:
                self._send_response(APIResponse(False, error="Not found"), 404)
                return

        # MIME type 判定
        suffix = target.suffix.lower()
        content_type = self._MIME_TYPES.get(suffix, "application/octet-stream")

        try:
            data = target.read_bytes()
        except OSError:
            self._send_response(APIResponse(False, error="Read error"), 500)
            return

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        origin = self._get_cors_origin(self.headers.get("Origin", ""))
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self) -> None:
        self.send_response(200)
        origin = self._get_cors_origin(self.headers.get('Origin', ''))
        if origin:
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Authorization, Content-Type, X-Rumi-CSRF, X-Rumi-Desktop-Bootstrap')
        self.end_headers()

    @classmethod
    def _get_allowed_origins(cls) -> list:
        """
        許可するオリジンリストを取得。
        環境変数 RUMI_CORS_ORIGINS (カンマ区切り) でカスタマイズ可能。
        未設定の場合は localhost の特定ポート(3000,5173,8080,8765)と
        RUMI_PORT で指定された実行時ポートのみ許可。
        ワイルドカードポート指定("http://localhost:*")は環境変数で
        明示的に指定した場合のみ有効。
        """
        env_origins = os.environ.get("RUMI_CORS_ORIGINS", "")
        runtime_port_raw = os.environ.get("RUMI_PORT", "")
        cache_key = (env_origins, runtime_port_raw)
        if cls._allowed_origins is not None and cls._allowed_origins_cache_key == cache_key:
            return cls._allowed_origins

        if env_origins.strip():
            cls._allowed_origins = [o.strip() for o in env_origins.split(",") if o.strip()]
            cls._allowed_origins_from_env = True
        else:
            cls._allowed_origins = [
                "http://localhost:3000",    # 一般的なフロントエンド開発ポート
                "http://localhost:5173",    # Vite デフォルト
                "http://localhost:8080",    # 一般的な開発ポート
                "http://localhost:8765",    # Pack API Server デフォルトポート
                "http://127.0.0.1:3000",
                "http://127.0.0.1:5173",
                "http://127.0.0.1:8080",
                "http://127.0.0.1:8765",
            ]
            if runtime_port_raw.strip():
                port = resolve_runtime_port()
                cls._allowed_origins.extend([
                    f"http://localhost:{port}",
                    f"http://127.0.0.1:{port}",
                ])
            cls._allowed_origins_from_env = False
        cls._allowed_origins = list(dict.fromkeys(cls._allowed_origins))
        cls._allowed_origins_cache_key = cache_key
        return cls._allowed_origins

    @classmethod
    def _get_cors_origin(cls, request_origin: str) -> str:
        """
        リクエストの Origin が許可リストに含まれていれば返す。
        含まれなければ空文字を返し、CORS ヘッダーを付与しない。
        """
        if not request_origin:
            return ""
        allowed = cls._get_allowed_origins()
        for pattern in allowed:
            if pattern == request_origin:
                return request_origin
            # "http://localhost:*" — ワイルドカードポート対応（環境変数で明示指定時のみ）
            if cls._allowed_origins_from_env and pattern.endswith(":*"):
                prefix = pattern[:-1]  # e.g. "http://localhost:"
                if request_origin.startswith(prefix):
                    return request_origin
        return ""

    
    def do_GET(self) -> None:
        _pre_auth_path = urlparse(self.path).path
        if not self._check_rate_limit(_pre_auth_path):
            return
        self._request_auth_mode = None
        self._panel_session = None
        self._panel_session_cookie = None

        # --- システムルート（テーブル化対象外）---
        if _pre_auth_path == "/health":
            _alm = self.__class__.app_lifecycle_manager
            if _alm is not None:
                _health = _alm.get_health()
            else:
                _health = {"status": "ok", "needs_setup": True}
            self._send_response(APIResponse(True, data=_health))
            return

        if _pre_auth_path == "/":
            self.send_response(302)
            self.send_header("Location", "/panel/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        # --- テーブル駆動: 静的配信 (web_mount) ---
        _wm = self._match_web_mount(_pre_auth_path)
        if _wm is not None:
            if _wm.get("auth_required", True):
                if self._check_web_mount_auth("GET", _wm):
                    self._serve_static_file(_pre_auth_path, _wm)
                    return
                if self._allows_public_bootstrap_page(_pre_auth_path, _wm):
                    self._serve_panel_bootstrap_page()
                    return
                self._send_response(APIResponse(False, error="Unauthorized"), 401)
                return
            self._serve_static_file(_pre_auth_path, _wm)
            return

        # --- テーブル駆動: pre-auth API ルート ---
        _is_pre_auth = self._is_pre_auth_route("GET", _pre_auth_path)

        if _is_pre_auth:
            # 認証不要ルート: ビジネスロジックはここで処理
            if _pre_auth_path == "/api/setup/status":
                _alm = self.__class__.app_lifecycle_manager
                if _alm is not None:
                    _setup_status = _alm.check_setup_status()
                else:
                    _setup_status = {"needs_setup": True, "reason": "lifecycle_manager_unavailable"}
                self._send_response(APIResponse(True, data=_setup_status))
                return

            # --- OAuth 2.1: 認可開始 (認証不要) ---
            if _pre_auth_path == "/api/setup/oauth/start":
                try:
                    oauth_start_result = self._oauth_start()
                    self._send_response(APIResponse(True, data=oauth_start_result))
                except Exception as e:
                    _log_internal_error("oauth_start", e)
                    self._send_response(APIResponse(False, error=_SAFE_ERROR_MSG), 500)
                return

            # --- OAuth 2.1: コールバック (認証不要) ---
            if _pre_auth_path == "/callback":
                try:
                    from urllib.parse import urlparse as _urlparse, parse_qs as _parse_qs
                    _cb_query = _parse_qs(_urlparse(self.path).query)
                    callback_result = self._oauth_callback(_cb_query)
                    if callback_result is None:
                        self._oauth_send_result_page(
                            "Rumi account connected",
                            "Sign-in completed successfully.",
                            success=True,
                        )
                    else:
                        _err_msg = callback_result.get("error", "unknown_error")
                        self._oauth_send_result_page(
                            "Rumi account connection failed",
                            _err_msg,
                            success=False,
                        )
                except Exception as e:
                    _log_internal_error("oauth_callback", e)
                    self._oauth_send_result_page(
                        "Rumi account connection failed",
                        "internal_error",
                        success=False,
                    )
                return

            # pre-auth テーブルにマッチしたが上記に該当しない場合
            # → 認証スキップして通常ルーティングへ通過

        # --- 認証チェック（pre-auth ルート以外）---
        if not _is_pre_auth and not self._check_auth("GET", _pre_auth_path):
            self._send_response(APIResponse(False, error="Unauthorized"), 401)
            return
        
        parsed = urlparse(self.path)
        path = parsed.path
        result: Any = None
        
        try:
            # --- api_routes テーブルディスパッチ (施策3) ---
            if self._dispatch_api_route("GET", path):
                return

            if path == "/api/packs":
                result = self._get_all_packs()
                self._send_result(result)
            
            elif path == "/api/packs/pending":
                result = self._get_pending_packs()
                self._send_result(result)
            
            elif path.startswith("/api/packs/") and path.endswith("/status"):
                pack_id = path.split("/")[3]
                if not self._validate_pack_id(pack_id):
                    self._send_response(APIResponse(False, error="Invalid pack_id"), 400)
                    return
                result = self._get_pack_status(pack_id)
                if result:
                    self._send_result(result)
                else:
                    self._send_response(APIResponse(False, error="Pack not found"), 404)
            
            elif path.startswith("/api/packs/") and path.endswith("/dependencies"):
                pack_id = path.split("/")[3]
                if not self._validate_pack_id(pack_id):
                    self._send_response(APIResponse(False, error="Invalid pack_id"), 400)
                    return
                result = self._get_pack_dependencies(pack_id)
                self._send_result(result)

            elif path == "/api/runtime/available":
                result = self._get_available_runtimes()
                self._send_result(result)

            elif path == "/api/containers":
                result = self._get_containers()
                self._send_result(result)
            
            elif path == "/api/privileges":
                result = self._get_privileges()
                self._send_result(result)
            
            elif path == "/api/docker/status":
                result = self._get_docker_status()
                self._send_result(result)

            elif path == "/api/network/list":
                result = self._network_list()
                self._send_result(result)

            elif path == "/api/secrets":
                result = self._secrets_list()
                self._send_result(result)

            # --- W19-B: Secret Grant GET endpoints ---
            elif path == "/api/secrets/grants":
                result = self._secrets_grants_list()
                self._send_result(result)

            elif path.startswith("/api/secrets/grants/"):
                # GET /api/secrets/grants/{pack_id}
                parts = path.strip("/").split("/")
                # parts: ["api", "secrets", "grants", "{pack_id}"]
                if len(parts) == 4:
                    pack_id = unquote(parts[3])
                    if not self._validate_pack_id(pack_id):
                        self._send_response(APIResponse(False, error="Invalid pack_id"), 400)
                        return
                    result = self._secrets_grants_get_pack(pack_id)
                    self._send_result(result)
                else:
                    self._send_response(APIResponse(False, error="Not found"), 404)


            elif path == "/api/stores":
                result = self._stores_list()
                self._send_result(result)


            elif path == "/api/stores/shared":
                result = self._stores_shared_list()
                self._send_result(result)

            elif path == "/api/units":
                query = parse_qs(urlparse(self.path).query)
                store_id = query.get("store_id", [""])[0]
                result = self._units_list(store_id)
                self._send_result(result)

            elif path == "/api/capability/blocked":
                result = self._capability_list_blocked()
                self._send_result(result)

            elif path == "/api/capability/grants":
                # GET /api/capability/grants?principal_id=xxx
                query = parse_qs(urlparse(self.path).query)
                principal_id = query.get("principal_id", [""])[0]
                result = self._capability_grants_list(principal_id)
                self._send_result(result)

            elif path == "/api/capability/requests":
                # GET /api/capability/requests?status=pending
                query = parse_qs(urlparse(self.path).query)
                status_filter = query.get("status", ["all"])[0]
                result = self._capability_list_requests(status_filter)
                self._send_result(result)

            elif path == "/api/pip/blocked":
                result = self._pip_list_blocked()
                self._send_result(result)

            elif path == "/api/pip/requests":
                # GET /api/pip/requests?status=pending
                query = parse_qs(urlparse(self.path).query)
                status_filter = query.get("status", ["all"])[0]
                result = self._pip_list_requests(status_filter)
                self._send_result(result)

            # --- Flow execution API ---
            elif path == "/api/flows":
                result = self._get_flow_list()
                self._send_result(result)

            # --- Pack custom routes (GET) ---
            elif path == "/api/routes":
                result = self._get_registered_routes()
                self._send_result(result)

            else:
                match = self._match_pack_route(path, "GET")
                if match:
                    self._handle_pack_route_request(path, {}, "GET", match)
                else:
                    logger.debug("Unmatched GET path: %s", path)
                    self._send_response(APIResponse(False, error="Not found"), 404)
                
        except Exception as e:
            _log_internal_error("do_GET", e)
            self._send_response(APIResponse(False, error=_SAFE_ERROR_MSG), 500)
    
    def do_POST(self) -> None:
        _pre_auth_path_post = urlparse(self.path).path
        if not self._check_rate_limit(_pre_auth_path_post):
            return
        self._request_auth_mode = None
        self._panel_session = None
        self._panel_session_cookie = None
        result: Any = None

        # --- テーブル駆動: pre-auth API ルート ---
        _is_pre_auth_post = self._is_pre_auth_route("POST", _pre_auth_path_post)

        if _is_pre_auth_post:
            # 認証不要ルート: ビジネスロジックはここで処理
            if _pre_auth_path_post == "/api/panel/auth/bootstrap":
                self._handle_panel_bootstrap()
                return

            if _pre_auth_path_post == "/api/panel/auth/exchange":
                _body_exchange = self._parse_body()
                if _body_exchange is None:
                    return
                self._handle_panel_exchange(_body_exchange)
                return

            if _pre_auth_path_post == "/api/setup/complete":
                _body_setup = self._parse_body()
                if _body_setup is None:
                    return
                _alm = self.__class__.app_lifecycle_manager
                if _alm is None:
                    self._send_response(APIResponse(False, error="Lifecycle manager not initialized"), 500)
                    return
                _setup_result = _alm.complete_setup(_body_setup)
                if _setup_result.get("success"):
                    try:
                        _k = self.__class__.kernel
                        if _k and hasattr(_k, 'event_bus') and _k.event_bus:
                            _k.event_bus.publish("setup.completed", {
                                "username": _body_setup.get("username"),
                                "language": _body_setup.get("language"),
                            })
                    except Exception:
                        pass
                    self._send_response(APIResponse(True, data=_setup_result))
                else:
                    _errors = _setup_result.get("errors", ["Setup failed"])
                    self._send_response(APIResponse(False, error="; ".join(_errors)), 400)
                return

            # pre-auth テーブルにマッチしたが上記に該当しない場合
            # → 認証スキップして通常ルーティングへ通過

        # --- 認証チェック（pre-auth ルート以外）---
        if not _is_pre_auth_post and not self._check_auth("POST", _pre_auth_path_post):
            self._discard_request_body()
            self._send_response(APIResponse(False, error="Unauthorized"), 401)
            return
        
        try:
            body = self._parse_body()
            if body is None:
                return  # レスポンス送信済み（サイズ超過 or JSONパース失敗）
            path = urlparse(self.path).path

            # --- api_routes テーブルディスパッチ (施策3) ---
            if self._dispatch_api_route("POST", path, body):
                return

            if path == "/api/network/grant":
                pack_id = body.get("pack_id", "")
                allowed_domains = body.get("allowed_domains", [])
                allowed_ports = body.get("allowed_ports", [])
                if not pack_id:
                    self._send_response(APIResponse(False, error="Missing pack_id"), 400)
                elif not self._validate_pack_id(pack_id):
                    self._send_response(APIResponse(False, error="Invalid pack_id"), 400)
                elif not allowed_domains and not allowed_ports:
                    self._send_response(APIResponse(False, error="Must specify allowed_domains or allowed_ports"), 400)
                else:
                    result = self._network_grant(
                        pack_id, allowed_domains, allowed_ports,
                        granted_by=body.get("granted_by", "api_user"),
                        notes=body.get("notes", ""),
                    )
                    if result.get("success"):
                        self._send_response(APIResponse(True, result))
                    else:
                        self._send_response(APIResponse(False, error=result.get("error", "Grant failed")), result.get("status_code", 400))

            elif path == "/api/network/revoke":
                pack_id = body.get("pack_id", "")
                if not pack_id:
                    self._send_response(APIResponse(False, error="Missing pack_id"), 400)
                elif not self._validate_pack_id(pack_id):
                    self._send_response(APIResponse(False, error="Invalid pack_id"), 400)
                else:
                    result = self._network_revoke(pack_id, reason=body.get("reason", ""))
                    if result.get("success"):
                        self._send_response(APIResponse(True, result))
                    else:
                        self._send_response(APIResponse(False, error=result.get("error", "Revoke failed")), result.get("status_code", 400))

            elif path == "/api/network/check":
                pack_id = body.get("pack_id", "")
                domain = body.get("domain", "")
                port = body.get("port")
                if not pack_id or not domain or port is None:
                    self._send_response(APIResponse(False, error="Missing pack_id, domain, or port"), 400)
                elif not self._validate_pack_id(pack_id):
                    self._send_response(APIResponse(False, error="Invalid pack_id"), 400)
                else:
                    result = self._network_check(pack_id, domain, int(port))
                    self._send_response(APIResponse(True, result))


            elif path == "/api/packs/scan":
                result = self._scan_packs()
                self._send_result(result)

            elif path == "/api/packs/import":
                source_path = body.get("path", "")
                notes = body.get("notes", "")
                if not source_path:
                    self._send_response(APIResponse(False, error="Missing 'path'"), 400)
                else:
                    # パストラバーサル防止: ecosystem/ 配下のみ許可
                    _eco_base = Path(
                        os.environ.get("RUMI_ECOSYSTEM_DIR", "ecosystem")
                    ).resolve()
                    try:
                        _resolved = Path(source_path).resolve()
                        _resolved.relative_to(_eco_base)
                    except (ValueError, OSError):
                        self._send_response(
                            APIResponse(False, error="Path must be within ecosystem directory"), 400
                        )
                        return
                    result = self._pack_import(source_path, notes)
                    if result.get("success"):
                        self._send_response(APIResponse(True, result))
                    else:
                        self._send_response(APIResponse(False, error=result.get("error")), result.get("status_code", 400))

            elif path == "/api/packs/apply":
                staging_id = body.get("staging_id", "")
                mode = body.get("mode", "replace")
                if not staging_id:
                    self._send_response(APIResponse(False, error="Missing 'staging_id'"), 400)
                elif not self._is_safe_id(staging_id):
                    self._send_response(APIResponse(False, error="Invalid staging_id"), 400)
                else:
                    result = self._pack_apply(staging_id, mode)
                    if result.get("success"):
                        self._send_response(APIResponse(True, result))
                    else:
                        self._send_response(APIResponse(False, error=result.get("error")), result.get("status_code", 400))

            elif path == "/api/secrets/set":
                result = self._secrets_set(body)
                if result.get("success"):
                    self._send_response(APIResponse(True, result))
                else:
                    self._send_response(APIResponse(False, error=result.get("error")), result.get("status_code", 400))

            elif path == "/api/secrets/delete":
                result = self._secrets_delete(body)
                if result.get("success"):
                    self._send_response(APIResponse(True, result))
                else:
                    self._send_response(APIResponse(False, error=result.get("error")), result.get("status_code", 400))

            # --- W19-B: Secret Grant POST endpoint ---
            elif path.startswith("/api/secrets/grants/"):
                # POST /api/secrets/grants/{pack_id}
                parts = path.strip("/").split("/")
                # parts: ["api", "secrets", "grants", "{pack_id}"]
                if len(parts) == 4:
                    pack_id = unquote(parts[3])
                    if not self._validate_pack_id(pack_id):
                        self._send_response(APIResponse(False, error="Invalid pack_id"), 400)
                        return
                    # pack_id を body に注入して既存ハンドラを呼び出す
                    body["pack_id"] = pack_id
                    result = self._secrets_grant(body)
                    if result.get("success"):
                        self._send_response(APIResponse(True, result))
                    else:
                        self._send_response(APIResponse(False, error=result.get("error")), result.get("status_code", 400))
                else:
                    self._send_response(APIResponse(False, error="Not found"), 404)


            elif path == "/api/stores/create":
                result = self._stores_create(body)
                if result.get("success"):
                    self._send_response(APIResponse(True, result))
                else:
                    self._send_response(APIResponse(False, error=result.get("error")), result.get("status_code", 400))

            elif path == "/api/units/publish":
                result = self._units_publish(body)
                if result.get("success"):
                    self._send_response(APIResponse(True, result))
                else:
                    self._send_response(APIResponse(False, error=result.get("error")), result.get("status_code", 400))

            elif path == "/api/units/execute":
                result = self._units_execute(body)
                if result.get("success"):
                    self._send_response(APIResponse(True, result))
                else:
                    status_code = 403 if result.get("error_type") in (
                        "approval_denied", "grant_denied", "trust_denied"
                    ) else 400
                    self._send_response(APIResponse(False, error=result.get("error")), result.get("status_code", status_code))

            elif path == "/api/pip/candidates/scan":
                ecosystem_dir = body.get("ecosystem_dir", None)
                result = self._pip_scan(ecosystem_dir)
                self._send_result(result)

            elif path.startswith("/api/pip/requests/") and path.endswith("/approve"):
                candidate_key = self._extract_capability_key(path, "/api/pip/requests/", "/approve")
                if candidate_key is None or not self._is_safe_id(candidate_key):
                    self._send_response(APIResponse(False, error="Invalid candidate_key"), 400)
                else:
                    allow_sdist = body.get("allow_sdist", False)
                    index_url = body.get("index_url", "https://pypi.org/simple")
                    result = self._pip_approve(candidate_key, allow_sdist, index_url)
                    if result.get("success"):
                        self._send_response(APIResponse(True, result))
                    else:
                        self._send_response(APIResponse(False, error=result.get("error", "Approve failed")), result.get("status_code", 400))

            elif path.startswith("/api/pip/requests/") and path.endswith("/reject"):
                candidate_key = self._extract_capability_key(path, "/api/pip/requests/", "/reject")
                if candidate_key is None or not self._is_safe_id(candidate_key):
                    self._send_response(APIResponse(False, error="Invalid candidate_key"), 400)
                else:
                    reason = body.get("reason", "")
                    result = self._pip_reject(candidate_key, reason)
                    if result.get("success"):
                        self._send_response(APIResponse(True, result))
                    else:
                        self._send_response(APIResponse(False, error=result.get("error", "Reject failed")), result.get("status_code", 400))

            elif path.startswith("/api/pip/blocked/") and path.endswith("/unblock"):
                candidate_key = self._extract_capability_key(path, "/api/pip/blocked/", "/unblock")
                if candidate_key is None or not self._is_safe_id(candidate_key):
                    self._send_response(APIResponse(False, error="Invalid candidate_key"), 400)
                else:
                    reason = body.get("reason", "")
                    result = self._pip_unblock(candidate_key, reason)
                    if result.get("success"):
                        self._send_response(APIResponse(True, result))
                    else:
                        self._send_response(APIResponse(False, error=result.get("error", "Unblock failed")), result.get("status_code", 400))

            elif path == "/api/capability/candidates/scan":
                ecosystem_dir = body.get("ecosystem_dir", None)
                result = self._capability_scan(ecosystem_dir)
                self._send_result(result)

            elif path.startswith("/api/capability/requests/") and path.endswith("/approve"):
                candidate_key = self._extract_capability_key(path, "/api/capability/requests/", "/approve")
                if candidate_key is None or not self._is_safe_id(candidate_key):
                    self._send_response(APIResponse(False, error="Invalid candidate_key"), 400)
                else:
                    notes = body.get("notes", "")
                    result = self._capability_approve(candidate_key, notes)
                    if result.get("success"):
                        self._send_response(APIResponse(True, result))
                    else:
                        self._send_response(APIResponse(False, error=result.get("error", "Approve failed")), result.get("status_code", 400))

            elif path.startswith("/api/capability/requests/") and path.endswith("/reject"):
                candidate_key = self._extract_capability_key(path, "/api/capability/requests/", "/reject")
                if candidate_key is None or not self._is_safe_id(candidate_key):
                    self._send_response(APIResponse(False, error="Invalid candidate_key"), 400)
                else:
                    reason = body.get("reason", "")
                    result = self._capability_reject(candidate_key, reason)
                    if result.get("success"):
                        self._send_response(APIResponse(True, result))
                    else:
                        self._send_response(APIResponse(False, error=result.get("error", "Reject failed")), result.get("status_code", 400))

            elif path.startswith("/api/capability/blocked/") and path.endswith("/unblock"):
                candidate_key = self._extract_capability_key(path, "/api/capability/blocked/", "/unblock")
                if candidate_key is None or not self._is_safe_id(candidate_key):
                    self._send_response(APIResponse(False, error="Invalid candidate_key"), 400)
                else:
                    reason = body.get("reason", "")
                    result = self._capability_unblock(candidate_key, reason)
                    if result.get("success"):
                        self._send_response(APIResponse(True, result))
                    else:
                        self._send_response(APIResponse(False, error=result.get("error", "Unblock failed")), result.get("status_code", 400))
            

            elif path == "/api/capability/grants/batch":
                grants_list = body.get("grants", [])
                result = self._capability_grants_batch(grants_list)
                if result.get("success"):
                    self._send_response(APIResponse(True, result))
                else:
                    self._send_response(APIResponse(False, error=result.get("error", "Batch grant failed")), result.get("status_code", 400))

            elif path == "/api/stores/shared/approve":
                provider_pack_id = body.get("provider_pack_id", "")
                consumer_pack_id = body.get("consumer_pack_id", "")
                store_id = body.get("store_id", "")
                result = self._stores_shared_approve(provider_pack_id, consumer_pack_id, store_id)
                if result.get("success"):
                    self._send_response(APIResponse(True, result))
                else:
                    self._send_response(APIResponse(False, error=result.get("error", "Approve failed")), result.get("status_code", 400))

            elif path == "/api/stores/shared/revoke":
                provider_pack_id = body.get("provider_pack_id", "")
                consumer_pack_id = body.get("consumer_pack_id", "")
                store_id = body.get("store_id", "")
                result = self._stores_shared_revoke(provider_pack_id, consumer_pack_id, store_id)
                if result.get("success"):
                    self._send_response(APIResponse(True, result))
                else:
                    self._send_response(APIResponse(False, error=result.get("error", "Revoke failed")), result.get("status_code", 400))

            elif path == "/api/capability/grants/grant":
                principal_id = body.get("principal_id", "")
                permission_id = body.get("permission_id", "")
                config = body.get("config")
                if not principal_id or not permission_id:
                    self._send_response(APIResponse(False, error="Missing principal_id or permission_id"), 400)
                else:
                    result = self._capability_grants_grant(principal_id, permission_id, config)
                    if result.get("success"):
                        self._send_response(APIResponse(True, result))
                    else:
                        self._send_response(APIResponse(False, error=result.get("error", "Grant failed")), result.get("status_code", 400))

            elif path == "/api/capability/grants/revoke":
                principal_id = body.get("principal_id", "")
                permission_id = body.get("permission_id", "")
                if not principal_id or not permission_id:
                    self._send_response(APIResponse(False, error="Missing principal_id or permission_id"), 400)
                else:
                    result = self._capability_grants_revoke(principal_id, permission_id)
                    if result.get("success"):
                        self._send_response(APIResponse(True, result))
                    else:
                        self._send_response(APIResponse(False, error=result.get("error", "Revoke failed")), result.get("status_code", 400))

            elif path.startswith("/api/packs/") and path.endswith("/approve"):
                pack_id = path.split("/")[3]
                if not self._validate_pack_id(pack_id):
                    self._send_response(APIResponse(False, error="Invalid pack_id"), 400)
                    return
                result = self._approve_pack(pack_id)
                if result.get("success"):
                    self._send_response(APIResponse(True, result))
                else:
                    self._send_response(APIResponse(False, error=result.get("error")), result.get("status_code", 400))
            
            elif path.startswith("/api/packs/") and path.endswith("/approve-rule"):
                pack_id = path.split("/")[3]
                if not self._validate_pack_id(pack_id):
                    self._send_response(APIResponse(False, error="Invalid pack_id"), 400)
                    return
                result = self._approve_rule_pack(pack_id)
                if isinstance(result, dict) and "error" in result:
                    self._send_response(
                        APIResponse(False, error=result["error"]),
                        result.get("status_code", 400),
                    )
                else:
                    self._send_response(APIResponse(True, data=result))

            elif path.startswith("/api/packs/") and path.endswith("/reject"):
                pack_id = path.split("/")[3]
                if not self._validate_pack_id(pack_id):
                    self._send_response(APIResponse(False, error="Invalid pack_id"), 400)
                    return
                reason = body.get("reason", "User rejected")
                result = self._reject_pack(pack_id, reason)
                self._send_result(result)
            
            elif path.startswith("/api/containers/") and path.endswith("/start"):
                pack_id = path.split("/")[3]
                if not self._validate_pack_id(pack_id):
                    self._send_response(APIResponse(False, error="Invalid pack_id"), 400)
                    return
                result = self._start_container(pack_id)
                if result.get("success"):
                    self._send_response(APIResponse(True, result))
                else:
                    self._send_response(APIResponse(False, error=result.get("error")), result.get("status_code", 400))
            
            elif path.startswith("/api/containers/") and path.endswith("/stop"):
                pack_id = path.split("/")[3]
                if not self._validate_pack_id(pack_id):
                    self._send_response(APIResponse(False, error="Invalid pack_id"), 400)
                    return
                result = self._stop_container(pack_id)
                self._send_result(result)
            
            elif path.startswith("/api/privileges/") and "/grant/" in path:
                parts = path.split("/")
                pack_id = parts[3]
                privilege_id = parts[5]
                if not self._validate_pack_id(pack_id):
                    self._send_response(APIResponse(False, error="Invalid pack_id"), 400)
                    return
                if not self._is_safe_id(privilege_id):
                    self._send_response(APIResponse(False, error="Invalid privilege_id"), 400)
                    return
                result = self._grant_privilege(pack_id, privilege_id)
                if result.get("success"):
                    self._send_response(APIResponse(True, result))
                else:
                    self._send_response(APIResponse(False, error=result.get("error")), result.get("status_code", 400))
            
            elif path.startswith("/api/privileges/") and "/execute/" in path:
                parts = path.split("/")
                pack_id = parts[3]
                privilege_id = parts[5]
                if not self._validate_pack_id(pack_id):
                    self._send_response(APIResponse(False, error="Invalid pack_id"), 400)
                    return
                if not self._is_safe_id(privilege_id):
                    self._send_response(APIResponse(False, error="Invalid privilege_id"), 400)
                    return
                params = body.get("params", {})
                result = self._execute_privilege(pack_id, privilege_id, params)
                if result.get("success"):
                    self._send_response(APIResponse(True, result))
                else:
                    self._send_response(APIResponse(False, error=result.get("error")), result.get("status_code", 403))

            # --- Route reload ---
            elif path == "/api/routes/reload":
                result = self._reload_pack_routes()
                self._send_result(result)

            # --- Flow execution API ---
            elif path.startswith("/api/flows/") and path.endswith("/run"):
                # flow_id バリデーション（flow_handlers 呼び出し前に検証）
                _flow_parts = path.split("/")
                if len(_flow_parts) >= 5:
                    _flow_id_raw = unquote(_flow_parts[3])
                    if not self._is_safe_id(_flow_id_raw):
                        self._send_response(APIResponse(False, error="Invalid flow_id"), 400)
                        return
                self._handle_flow_run(path, body)

            # --- Pack custom routes (POST) ---
            else:
                match = self._match_pack_route(path, "POST")
                if match:
                    self._handle_pack_route_request(path, body, "POST", match)
                else:
                    logger.debug("Unmatched POST path: %s", path)
                    self._send_response(APIResponse(False, error="Not found"), 404)
                
        except Exception as e:
            _log_internal_error("do_POST", e)
            self._send_response(APIResponse(False, error=_SAFE_ERROR_MSG), 500)
    

    def do_PUT(self) -> None:
        """PUT メソッド — Panel API + Pack独自ルート"""
        _pre_auth_path_put = urlparse(self.path).path
        if not self._check_rate_limit(_pre_auth_path_put):
            return
        self._request_auth_mode = None
        self._panel_session = None
        self._panel_session_cookie = None
        result: Any = None
        # --- テーブル駆動: 認証チェック ---
        if not self._is_pre_auth_route("PUT", _pre_auth_path_put) and not self._check_auth("PUT", _pre_auth_path_put):
            self._discard_request_body()
            self._send_response(APIResponse(False, error="Unauthorized"), 401)
            return

        try:
            body = self._parse_body()
            if body is None:
                return  # レスポンス送信済み
            path = urlparse(self.path).path

            # --- api_routes テーブルディスパッチ (施策3) ---
            if self._dispatch_api_route("PUT", path, body):
                return

            match = self._match_pack_route(path, "PUT")
            if match:
                self._handle_pack_route_request(path, body, "PUT", match)
            else:
                logger.debug("Unmatched PUT path: %s", path)
                self._send_response(APIResponse(False, error="Not found"), 404)

        except Exception as e:
            _log_internal_error("do_PUT", e)
            self._send_response(APIResponse(False, error=_SAFE_ERROR_MSG), 500)
    def do_DELETE(self) -> None:
        _pre_auth_path_del = urlparse(self.path).path
        if not self._check_rate_limit(_pre_auth_path_del):
            return
        self._request_auth_mode = None
        self._panel_session = None
        self._panel_session_cookie = None
        result: Any = None
        # --- テーブル駆動: 認証チェック ---
        if not self._is_pre_auth_route("DELETE", _pre_auth_path_del) and not self._check_auth("DELETE", _pre_auth_path_del):
            self._send_response(APIResponse(False, error="Unauthorized"), 401)
            return
        
        path = urlparse(self.path).path
        
        try:
            # --- api_routes テーブルディスパッチ (施策3) ---
            if self._dispatch_api_route("DELETE", path):
                return

            # --- W19-B: Secret Grant DELETE endpoints ---
            if path.startswith("/api/secrets/grants/"):
                parts = path.strip("/").split("/")
                # DELETE /api/secrets/grants/{pack_id}/{secret_key} (5 parts)
                if len(parts) == 5:
                    pack_id = unquote(parts[3])
                    secret_key = unquote(parts[4])
                    if not self._validate_pack_id(pack_id):
                        self._send_response(APIResponse(False, error="Invalid pack_id"), 400)
                        return
                    result = self._secrets_grants_delete_key(pack_id, secret_key)
                    self._send_result(result)
                # DELETE /api/secrets/grants/{pack_id} (4 parts)
                elif len(parts) == 4:
                    pack_id = unquote(parts[3])
                    if not self._validate_pack_id(pack_id):
                        self._send_response(APIResponse(False, error="Invalid pack_id"), 400)
                        return
                    result = self._secrets_grants_delete_pack(pack_id)
                    self._send_result(result)
                else:
                    self._send_response(APIResponse(False, error="Not found"), 404)

            elif path.startswith("/api/containers/"):
                pack_id = path.split("/")[3]
                if not self._validate_pack_id(pack_id):
                    self._send_response(APIResponse(False, error="Invalid pack_id"), 400)
                    return
                result = self._remove_container(pack_id)
                self._send_result(result)

            elif path.startswith("/api/packs/"):
                parts = path.strip("/").split("/")
                # DELETE /api/packs/{pack_id} (exactly 3 segments: api/packs/{id})
                if len(parts) == 3:
                    pack_id = parts[2]
                    if not self._validate_pack_id(pack_id):
                        self._send_response(APIResponse(False, error="Invalid pack_id"), 400)
                    else:
                        result = self._uninstall_pack(pack_id)
                        self._send_result(result)
                else:
                    self._send_response(APIResponse(False, error="Not found"), 404)

            else:
                # T-009: Pack独自ルートフォールバック
                match = self._match_pack_route(path, "DELETE")
                if match:
                    body = self._parse_body()
                    if body is None:
                        return  # レスポンス送信済み
                    self._handle_pack_route_request(path, body, "DELETE", match)
                else:
                    logger.debug("Unmatched DELETE path: %s", path)
                    self._send_response(APIResponse(False, error="Not found"), 404)
                
        except Exception as e:
            _log_internal_error("do_DELETE", e)
            self._send_response(APIResponse(False, error=_SAFE_ERROR_MSG), 500)
class PackAPIServer:
    
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        approval_manager = None,
        container_orchestrator = None,
        host_privilege_manager = None,
        internal_token: Optional[str] = None,
        kernel = None,
        app_lifecycle_manager = None
    ):
        self.kernel = kernel
        self.app_lifecycle_manager = app_lifecycle_manager
        # Fix #3: bind address restriction — env var override + 0.0.0.0 warning
        resolved_host = os.environ.get("RUMI_API_BIND_ADDRESS", host) or "127.0.0.1"
        if resolved_host == "0.0.0.0":
            logger.warning(
                "SECURITY WARNING: API server binding to 0.0.0.0 (all interfaces). "
                "This exposes the API to the network. Use 127.0.0.1 for local-only access."
            )
            try:
                from .audit_logger import get_audit_logger
                audit = get_audit_logger()
                audit.log_system_event(
                    event_type="api_bind_all_interfaces",
                    success=True,
                    details={"bind_address": "0.0.0.0", "warning": "Exposed to network"},
                )
            except Exception:
                pass
        self.host = resolved_host
        self.port = port
        self.approval_manager = approval_manager
        self.container_orchestrator = container_orchestrator
        self.host_privilege_manager = host_privilege_manager
        
        # HMAC鍵管理: HMACKeyManager を使用
        self._hmac_key_manager = get_hmac_key_manager()
        self._panel_auth_manager = get_panel_auth_manager()
        
        if internal_token is None:
            # HMACKeyManager からアクティブ鍵を取得
            internal_token = self._hmac_key_manager.get_active_key()
            token_prefix = internal_token[:8] + "..." if internal_token and len(internal_token) >= 8 else internal_token or "(empty)"
            logger.info("Using HMAC-managed API token (prefix): %s", token_prefix)
            logger.warning("To retrieve the full token, inspect: user_data/hmac_keys.json")
            logger.warning('  Or run: python3 -c "from core_runtime.hmac_key_manager import HMACKeyManager; m=HMACKeyManager(); print(m.get_active_key())"')
            logger.warning("Set this token in client requests: Authorization: Bearer <your-token>")
            logger.warning("Token rotation: set RUMI_HMAC_ROTATE=true and restart")
        
        self.internal_token = internal_token
        self.server: Optional[_PackThreadingHTTPServer] = None
        self.thread: Optional[threading.Thread] = None
        self._routes_load_lock = threading.Lock()
    
    def start(self) -> None:
        PackAPIHandler.approval_manager = self.approval_manager
        PackAPIHandler.container_orchestrator = self.container_orchestrator
        PackAPIHandler.host_privilege_manager = self.host_privilege_manager
        PackAPIHandler.internal_token = self.internal_token
        PackAPIHandler._hmac_key_manager = self._hmac_key_manager
        PackAPIHandler._panel_auth_manager = self._panel_auth_manager
        PackAPIHandler.kernel = self.kernel
        PackAPIHandler.app_lifecycle_manager = self.app_lifecycle_manager

        # BUG-20260306-02 fix: Pack ルートの読み込みを system.ready イベント後に遅延実行する。
        # API サーバー自体は security phase で初期化し、Pack ルートは
        # component setup 完了後にロードされる。
        # event_bus が利用可能ならイベント駆動、なければ即時ロード。
        self._routes_loaded = False
        try:
            from backend_core.ecosystem.registry import get_registry

            reg = get_registry()
            PackAPIHandler.load_web_mounts(reg, pack_ids={"core_control_panel"})
            PackAPIHandler.load_pre_auth_routes(reg, pack_ids={"core_control_panel"})
            logger.info("Preloaded control panel shell routes before runtime-ready")
        except Exception as e:
            logger.warning("Failed to preload control panel shell routes: %s", e)
        try:
            if self.kernel and hasattr(self.kernel, 'event_bus') and self.kernel.event_bus:
                def _deferred_load_routes(event_data=None):
                    with self._routes_load_lock:
                        if not self._routes_loaded:
                            self._routes_loaded = True
                            try:
                                from backend_core.ecosystem.registry import get_registry
                                reg = get_registry()
                                PackAPIHandler.load_pack_routes(reg)
                                PackAPIHandler.load_web_mounts(reg)
                                PackAPIHandler.load_pre_auth_routes(reg)
                                PackAPIHandler.load_api_routes(reg)
                                logger.info("Pack routes loaded (deferred after system.ready)")
                            except Exception as e:
                                logger.warning("Failed to load pack routes (deferred): %s", e)
                self.kernel.event_bus.subscribe("system.ready", _deferred_load_routes)
            else:
                # Fallback: event_bus なしの場合は即時ロード
                try:
                    from backend_core.ecosystem.registry import get_registry
                    reg = get_registry()
                    PackAPIHandler.load_pack_routes(reg)
                    PackAPIHandler.load_web_mounts(reg)
                    PackAPIHandler.load_pre_auth_routes(reg)
                    PackAPIHandler.load_api_routes(reg)
                    self._routes_loaded = True
                except Exception as e:
                    logger.warning("Failed to load pack routes: %s", e)
        except Exception as e:
            logger.warning("Failed to set up deferred route loading: %s", e)
        
        self.server = _PackThreadingHTTPServer((self.host, self.port), PackAPIHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        logger.info("Pack API server started on http://%s:%s", self.host, self.port)
    
    def stop(self) -> None:
        if self.server:
            server = self.server
            server.shutdown()
            server.server_close()
            self.server = None
        if self.thread:
            self.thread.join(timeout=THREAD_JOIN_TIMEOUT_SECONDS)
            self.thread = None
        logger.info("Pack API server stopped")
    
    def is_running(self) -> bool:
        return self.server is not None and self.thread is not None and self.thread.is_alive()


_api_server: Optional[PackAPIServer] = None


def get_pack_api_server() -> Optional[PackAPIServer]:
    """
    グローバルな PackAPIServer を取得する。

    DI コンテナ経由で取得を試み、未初期化なら None を返す。
    """
    from .di_container import get_container
    instance = get_container().get_or_none("pack_api_server")
    if instance is not None:
        return instance
    return _api_server


def initialize_pack_api_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    approval_manager = None,
    container_orchestrator = None,
    host_privilege_manager = None,
    internal_token: Optional[str] = None,
    kernel = None,
    app_lifecycle_manager = None
) -> PackAPIServer:
    global _api_server
    
    if _api_server is not None:
        _api_server.stop()
    
    _api_server = PackAPIServer(
        host=host,
        port=port,
        approval_manager=approval_manager,
        container_orchestrator=container_orchestrator,
        host_privilege_manager=host_privilege_manager,
        internal_token=internal_token,
        kernel=kernel,
        app_lifecycle_manager=app_lifecycle_manager
    )
    _api_server.start()
    # DI コンテナのキャッシュも更新
    from .di_container import get_container
    get_container().set_instance("pack_api_server", _api_server)
    return _api_server


def shutdown_pack_api_server() -> None:
    global _api_server
    if _api_server:
        _api_server.stop()
        _api_server = None
    # DI コンテナのキャッシュもクリア
    try:
        from .di_container import get_container
        get_container().reset("pack_api_server")
    except Exception:
        pass
