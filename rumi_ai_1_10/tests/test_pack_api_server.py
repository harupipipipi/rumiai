"""
test_pack_api_server.py — pack_api_server.py のユニットテスト

テスト対象:
- PackAPIHandler: バリデーション関数, 認証, ボディ読み取り/パース, CORS
- PackAPIServer: インスタンス化, 属性設定
- モジュールレベル定数: PACK_ID_RE, SAFE_ID_RE, MAX_REQUEST_BODY_BYTES
"""
from __future__ import annotations

import io
import json
import threading
import time
import urllib.request
from email.message import Message
from http.server import ThreadingHTTPServer
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from core_runtime.pack_api_server import (
    PackAPIHandler,
    PackAPIServer,
    PACK_ID_RE,
    SAFE_ID_RE,
    MAX_REQUEST_BODY_BYTES,
    THREAD_JOIN_TIMEOUT_SECONDS,
    _rate_limiter,
)
from core_runtime.api.api_response import APIResponse
from core_runtime.panel_auth import PanelAuthManager, reset_panel_auth_manager_for_tests


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_handler(**attrs) -> PackAPIHandler:
    """BaseHTTPRequestHandler.__init__ をバイパスして PackAPIHandler を作成する。

    ``__init__`` は request を受け取り即 handle() を呼ぶため、
    テストでは ``object.__new__`` でインスタンスを作り属性を手動設定する。
    """
    handler = object.__new__(PackAPIHandler)
    # デフォルトのモック属性
    handler.headers = Message()
    handler.rfile = io.BytesIO(b"")
    handler.wfile = io.BytesIO()
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    handler._send_response = MagicMock()
    # クラス属性をインスタンスに設定（テスト間分離のため）
    handler._hmac_key_manager = None
    handler.internal_token = ""
    # カスタム属性を上書き
    for k, v in attrs.items():
        setattr(handler, k, v)
    return handler


def _make_headers(**fields) -> Message:
    """email.message.Message をヘッダーとして構築する。"""
    msg = Message()
    for key, value in fields.items():
        msg[key.replace("_", "-")] = value
    return msg


class _FlushBytesIO(io.BytesIO):
    def __init__(self) -> None:
        super().__init__()
        self.flush_count = 0

    def flush(self) -> None:
        self.flush_count += 1
        super().flush()


# ---------------------------------------------------------------------------
# 1-2. pack_id バリデーション
# ---------------------------------------------------------------------------

class TestValidatePackId:
    @pytest.mark.parametrize("pack_id", [
        "my_pack",
        "my-pack",
        "Pack123",
        "a",
        "A" * 64,
        "test_pack-01",
    ])
    def test_valid_pack_ids(self, pack_id: str) -> None:
        assert PackAPIHandler._validate_pack_id(pack_id) is True

    @pytest.mark.parametrize("pack_id", [
        "",
        "A" * 65,
        "pack/traversal",
        "pack..id",
        "pack id",
        "../etc/passwd",
        "pack@name",
        None,
    ])
    def test_invalid_pack_ids(self, pack_id) -> None:
        assert PackAPIHandler._validate_pack_id(pack_id) is False


# ---------------------------------------------------------------------------
# 3-4. safe_id バリデーション
# ---------------------------------------------------------------------------

class TestIsSafeId:
    @pytest.mark.parametrize("value", [
        "simple",
        "with_underscore",
        "with.dot",
        "with:colon",
        "with/slash",
        "with-dash",
        "a" * 256,
        "flow:my_pack/step1",
    ])
    def test_valid_safe_ids(self, value: str) -> None:
        assert PackAPIHandler._is_safe_id(value) is True

    @pytest.mark.parametrize("value", [
        "",
        "a" * 257,
        "with space",
        "with@at",
        "with#hash",
        None,
    ])
    def test_invalid_safe_ids(self, value) -> None:
        assert PackAPIHandler._is_safe_id(value) is False


class TestSSEResponses:
    def test_send_result_streams_defaultspack_sse_events_incrementally(self) -> None:
        wfile = _FlushBytesIO()
        handler = _make_handler(
            headers=_make_headers(Origin="http://127.0.0.1:8765"),
            wfile=wfile,
            _panel_session_cookie=None,
        )

        handler._send_result(
            {
                "status": "ok",
                "data": {
                    "_sse": True,
                    "events": [
                        {"type": "delta", "delta": "hello"},
                        {"type": "done"},
                    ],
                },
            }
        )

        assert handler.send_response.call_args.args == (200,)
        sent_headers = [call.args for call in handler.send_header.call_args_list]
        assert ("Content-Type", "text/event-stream; charset=utf-8") in sent_headers
        assert ("Cache-Control", "no-cache, no-transform") in sent_headers
        assert ("Connection", "close") in sent_headers
        assert ("Content-Length", str(len(wfile.getvalue()))) not in sent_headers
        assert wfile.getvalue() == (
            b'data: {"type": "delta", "delta": "hello"}\n\n'
            b'data: {"type": "done"}\n\n'
        )
        assert wfile.flush_count == 2
        assert handler.close_connection is True


# ---------------------------------------------------------------------------
# 5-9. 認証 (_check_auth)
# ---------------------------------------------------------------------------

class _DisconnectedWriter:
    def __init__(self, exc: Exception):
        self.exc = exc

    def write(self, data) -> None:
        raise self.exc

    def flush(self) -> None:
        raise self.exc


class TestClientDisconnectHandling:
    def test_send_response_handles_header_connection_abort(self) -> None:
        handler = _make_handler(headers=_make_headers())
        handler.close_connection = False
        handler.end_headers.side_effect = ConnectionAbortedError(
            10053,
            "connection aborted",
        )

        PackAPIHandler._send_response(
            handler,
            APIResponse(True, data={"ok": True}),
        )

        assert handler.close_connection is True

    def test_send_raw_json_handles_body_connection_reset(self) -> None:
        handler = _make_handler(headers=_make_headers())
        handler.close_connection = False
        handler.wfile = _DisconnectedWriter(
            ConnectionResetError(10054, "connection reset by peer"),
        )

        handler._send_raw_json({"ok": True})

        assert handler.close_connection is True

    def test_send_sse_handles_broken_pipe(self) -> None:
        handler = _make_handler(headers=_make_headers())
        handler.close_connection = False
        handler.wfile = _DisconnectedWriter(BrokenPipeError(10054, "broken pipe"))

        handler._send_sse([{"type": "done"}])

        assert handler.close_connection is True


class TestCheckAuth:
    def test_auth_success_hmac_manager(self) -> None:
        """HMACKeyManager.verify_token が True を返す → 認証成功"""
        mock_mgr = MagicMock()
        mock_mgr.verify_token.return_value = True
        handler = _make_handler(
            headers=_make_headers(Authorization="Bearer my-secret-token"),
            _hmac_key_manager=mock_mgr,
        )
        assert handler._check_auth("GET", "/api/packs") is True
        mock_mgr.verify_token.assert_called_once_with("my-secret-token")

    def test_auth_failure_no_header(self) -> None:
        """Authorization ヘッダーなし → 認証失敗"""
        handler = _make_handler(headers=_make_headers())
        assert handler._check_auth("GET", "/api/packs") is False

    def test_auth_failure_no_bearer_prefix(self) -> None:
        """Bearer プレフィックスなし → 認証失敗"""
        handler = _make_handler(
            headers=_make_headers(Authorization="Basic abc123"),
        )
        assert handler._check_auth("GET", "/api/packs") is False

    def test_auth_fallback_internal_token_success(self) -> None:
        """HMACKeyManager=None, internal_token で一致 → 成功"""
        handler = _make_handler(
            headers=_make_headers(Authorization="Bearer fallback-token"),
            _hmac_key_manager=None,
            internal_token="fallback-token",
        )
        assert handler._check_auth("GET", "/api/packs") is True

    def test_auth_fallback_internal_token_mismatch(self) -> None:
        """HMACKeyManager=None, internal_token 不一致 → 失敗"""
        handler = _make_handler(
            headers=_make_headers(Authorization="Bearer wrong-token"),
            _hmac_key_manager=None,
            internal_token="correct-token",
        )
        assert handler._check_auth("GET", "/api/packs") is False

    def test_auth_fallback_no_internal_token_configured(self) -> None:
        """HMACKeyManager=None, internal_token="" → 失敗"""
        handler = _make_handler(
            headers=_make_headers(Authorization="Bearer some-token"),
            _hmac_key_manager=None,
            internal_token="",
        )
        assert handler._check_auth("GET", "/api/packs") is False

    def test_panel_session_auth_success_for_get(self) -> None:
        panel_mgr = PanelAuthManager(bootstrap_secret="bootstrap")
        reset_panel_auth_manager_for_tests(panel_mgr)
        issue = panel_mgr.issue_login_code()
        exchange = panel_mgr.exchange_code(issue["code"])
        assert exchange is not None

        handler = _make_handler(
            headers=_make_headers(Cookie=f"rumi_panel_session={exchange['session_id']}"),
            _panel_auth_manager=panel_mgr,
        )

        assert handler._check_auth("GET", "/api/panel/dashboard") is True
        assert handler._request_auth_mode == "panel_session"

    def test_panel_session_auth_refreshes_cookie_ttl_on_response(self) -> None:
        panel_mgr = PanelAuthManager(bootstrap_secret="bootstrap")
        reset_panel_auth_manager_for_tests(panel_mgr)
        issue = panel_mgr.issue_login_code()
        exchange = panel_mgr.exchange_code(issue["code"])
        assert exchange is not None

        handler = _make_handler(
            headers=_make_headers(Cookie=f"rumi_panel_session={exchange['session_id']}"),
            _panel_auth_manager=panel_mgr,
        )

        assert handler._check_auth("GET", "/api/panel/dashboard") is True
        assert handler._panel_session_cookie is not None
        assert exchange["session_id"] in handler._panel_session_cookie
        assert "Max-Age=28800" in handler._panel_session_cookie

        PackAPIHandler._send_response(handler, APIResponse(True, data={"ok": True}))

        assert ("Set-Cookie", handler._panel_session_cookie) in [
            call.args for call in handler.send_header.call_args_list
        ]

    def test_panel_session_mutation_requires_csrf_and_origin(self) -> None:
        panel_mgr = PanelAuthManager(bootstrap_secret="bootstrap")
        reset_panel_auth_manager_for_tests(panel_mgr)
        issue = panel_mgr.issue_login_code()
        exchange = panel_mgr.exchange_code(issue["code"])
        assert exchange is not None

        handler = _make_handler(
            headers=_make_headers(
                Cookie=f"rumi_panel_session={exchange['session_id']}",
                Origin="http://127.0.0.1:8765",
                X_Rumi_Csrf=exchange["csrf_token"],
            ),
            _panel_auth_manager=panel_mgr,
        )

        assert handler._check_auth("POST", "/api/panel/kernel/restart") is True

    def test_panel_session_mutation_rejects_missing_csrf(self) -> None:
        panel_mgr = PanelAuthManager(bootstrap_secret="bootstrap")
        reset_panel_auth_manager_for_tests(panel_mgr)
        issue = panel_mgr.issue_login_code()
        exchange = panel_mgr.exchange_code(issue["code"])
        assert exchange is not None

        handler = _make_handler(
            headers=_make_headers(
                Cookie=f"rumi_panel_session={exchange['session_id']}",
                Origin="http://127.0.0.1:8765",
            ),
            _panel_auth_manager=panel_mgr,
        )

        assert handler._check_auth("POST", "/api/panel/kernel/restart") is False

    def test_web_mount_auth_uses_panel_session_for_control_panel(self) -> None:
        panel_mgr = PanelAuthManager(bootstrap_secret="bootstrap")
        reset_panel_auth_manager_for_tests(panel_mgr)
        issue = panel_mgr.issue_login_code()
        exchange = panel_mgr.exchange_code(issue["code"])
        assert exchange is not None

        handler = _make_handler(
            headers=_make_headers(Cookie=f"rumi_panel_session={exchange['session_id']}"),
            _panel_auth_manager=panel_mgr,
        )

        assert handler._check_web_mount_auth(
            "GET",
            {"pack_id": "core_control_panel", "path_prefix": "/panel"},
        ) is True
        assert handler._request_auth_mode == "panel_session"

    def test_public_panel_bootstrap_page_is_only_allowed_for_root_document(self) -> None:
        web_mount = {"pack_id": "core_control_panel", "path_prefix": "/panel"}

        assert PackAPIHandler._allows_public_bootstrap_page("/panel", web_mount) is True
        assert PackAPIHandler._allows_public_bootstrap_page("/panel/", web_mount) is True
        assert PackAPIHandler._allows_public_bootstrap_page("/panel/index.html", web_mount) is True
        assert PackAPIHandler._allows_public_bootstrap_page("/panel/assets/app.js", web_mount) is False

    def test_log_message_redacts_sensitive_query_params(self) -> None:
        handler = _make_handler()

        with patch("core_runtime.pack_api_server.logger.info") as mocked:
            handler.log_message(
                '"%s" %s %s',
                "GET /panel/?code=secret-code&token=secret-token HTTP/1.1",
                "200",
                "123",
            )

        mocked.assert_called_once()
        logged_message = mocked.call_args.args[1]
        assert "[REDACTED]" in logged_message
        assert "secret-code" not in logged_message
        assert "secret-token" not in logged_message


# ---------------------------------------------------------------------------
# 10-12. _read_raw_body
# ---------------------------------------------------------------------------

class TestReadRawBody:
    def test_read_normal(self) -> None:
        """正常なボディ読み取り"""
        body = b'{"key": "value"}'
        handler = _make_handler(
            headers=_make_headers(Content_Length=str(len(body))),
            rfile=io.BytesIO(body),
        )
        result = handler._read_raw_body()
        assert result == body
        assert handler._raw_body_bytes == body

    def test_read_empty_body(self) -> None:
        """Content-Length=0 → 空バイト列"""
        handler = _make_handler(
            headers=_make_headers(Content_Length="0"),
            rfile=io.BytesIO(b""),
        )
        result = handler._read_raw_body()
        assert result == b""

    def test_read_invalid_content_length(self) -> None:
        """Content-Length が数値でない → 400"""
        handler = _make_handler(
            headers=_make_headers(Content_Length="not-a-number"),
        )
        result = handler._read_raw_body()
        assert result is None
        handler._send_response.assert_called_once()
        call_args = handler._send_response.call_args
        resp: APIResponse = call_args[0][0]
        assert resp.success is False
        assert "Invalid Content-Length" in resp.error
        assert call_args[0][1] == 400

    def test_read_negative_content_length(self) -> None:
        """Content-Length が負値 → 400"""
        handler = _make_handler(
            headers=_make_headers(Content_Length="-1"),
        )
        result = handler._read_raw_body()
        assert result is None
        handler._send_response.assert_called_once()

    def test_read_body_too_large(self) -> None:
        """Content-Length がサイズ上限超過 → 413"""
        handler = _make_handler(
            headers=_make_headers(
                Content_Length=str(MAX_REQUEST_BODY_BYTES + 1)
            ),
        )
        result = handler._read_raw_body()
        assert result is None
        call_args = handler._send_response.call_args
        resp: APIResponse = call_args[0][0]
        assert resp.success is False
        assert "too large" in resp.error
        assert call_args[0][1] == 413


# ---------------------------------------------------------------------------
# 13-14. _parse_body
# ---------------------------------------------------------------------------

class TestParseBody:
    def test_parse_valid_json(self) -> None:
        """正常な JSON ボディ → dict"""
        body = b'{"name": "test", "value": 42}'
        handler = _make_handler(
            headers=_make_headers(Content_Length=str(len(body))),
            rfile=io.BytesIO(body),
        )
        result = handler._parse_body()
        assert result == {"name": "test", "value": 42}

    def test_parse_empty_body(self) -> None:
        """空ボディ → 空 dict"""
        handler = _make_handler(
            headers=_make_headers(Content_Length="0"),
            rfile=io.BytesIO(b""),
        )
        result = handler._parse_body()
        assert result == {}

    def test_parse_invalid_json(self) -> None:
        """不正な JSON → None (400 レスポンス送信済み)"""
        body = b'{invalid json'
        handler = _make_handler(
            headers=_make_headers(Content_Length=str(len(body))),
            rfile=io.BytesIO(body),
        )
        result = handler._parse_body()
        assert result is None
        handler._send_response.assert_called_once()
        call_args = handler._send_response.call_args
        resp: APIResponse = call_args[0][0]
        assert resp.success is False
        assert "Invalid JSON" in resp.error
        assert call_args[0][1] == 400


# ---------------------------------------------------------------------------
# 15-17. CORS
# ---------------------------------------------------------------------------

class TestCORS:
    @pytest.fixture(autouse=True)
    def _reset_cors_cache(self):
        """各テスト前後で CORS キャッシュをリセット"""
        PackAPIHandler._allowed_origins = None
        PackAPIHandler._allowed_origins_from_env = False
        PackAPIHandler._allowed_origins_cache_key = None
        yield
        PackAPIHandler._allowed_origins = None
        PackAPIHandler._allowed_origins_from_env = False
        PackAPIHandler._allowed_origins_cache_key = None

    def test_cors_allowed_default(self, monkeypatch) -> None:
        """デフォルト許可リストに含まれるオリジン → 返却"""
        monkeypatch.delenv("RUMI_CORS_ORIGINS", raising=False)
        result = PackAPIHandler._get_cors_origin("http://localhost:3000")
        assert result == "http://localhost:3000"

    def test_cors_disallowed_origin(self, monkeypatch) -> None:
        """デフォルト許可リストに含まれないオリジン → 空文字"""
        monkeypatch.delenv("RUMI_CORS_ORIGINS", raising=False)
        monkeypatch.delenv("RUMI_PORT", raising=False)
        result = PackAPIHandler._get_cors_origin("http://evil.com")
        assert result == ""

    def test_cors_allows_runtime_rumi_port(self, monkeypatch) -> None:
        """RUMI_PORT の実行時ポートは panel 認証 Origin として許可"""
        monkeypatch.delenv("RUMI_CORS_ORIGINS", raising=False)
        monkeypatch.setenv("RUMI_PORT", "8768")
        assert PackAPIHandler._get_cors_origin("http://127.0.0.1:8768") == "http://127.0.0.1:8768"
        assert PackAPIHandler._get_cors_origin("http://localhost:8768") == "http://localhost:8768"

    def test_cors_recomputes_when_runtime_port_env_changes(self, monkeypatch) -> None:
        """同一process内で RUMI_PORT が変わったら許可originを再計算"""
        monkeypatch.delenv("RUMI_CORS_ORIGINS", raising=False)
        monkeypatch.setenv("RUMI_PORT", "8768")
        assert PackAPIHandler._get_cors_origin("http://localhost:8768") == "http://localhost:8768"

        monkeypatch.setenv("RUMI_PORT", "8771")
        assert PackAPIHandler._get_cors_origin("http://localhost:8771") == "http://localhost:8771"
        assert PackAPIHandler._get_cors_origin("http://localhost:8768") == ""

    def test_cors_invalid_runtime_port_falls_back_to_default(self, monkeypatch) -> None:
        """不正な RUMI_PORT は落とさずデフォルトoriginだけ許可"""
        monkeypatch.delenv("RUMI_CORS_ORIGINS", raising=False)
        monkeypatch.setenv("RUMI_PORT", "not-a-port")
        assert PackAPIHandler._get_cors_origin("http://localhost:8765") == "http://localhost:8765"
        assert PackAPIHandler._get_cors_origin("http://localhost:8768") == ""

    def test_cors_empty_origin(self, monkeypatch) -> None:
        """オリジン空文字 → 空文字"""
        monkeypatch.delenv("RUMI_CORS_ORIGINS", raising=False)
        result = PackAPIHandler._get_cors_origin("")
        assert result == ""

    def test_cors_env_custom_origins(self, monkeypatch) -> None:
        """環境変数でカスタムオリジン指定"""
        monkeypatch.setenv("RUMI_CORS_ORIGINS", "https://myapp.com,https://other.com")
        result = PackAPIHandler._get_cors_origin("https://myapp.com")
        assert result == "https://myapp.com"

    def test_cors_env_wildcard_port(self, monkeypatch) -> None:
        """環境変数でワイルドカードポート指定 → 任意ポート許可"""
        monkeypatch.setenv("RUMI_CORS_ORIGINS", "http://localhost:*")
        result = PackAPIHandler._get_cors_origin("http://localhost:9999")
        assert result == "http://localhost:9999"

    def test_cors_wildcard_not_from_env(self, monkeypatch) -> None:
        """デフォルトリストでは "http://localhost:*" は効かない"""
        monkeypatch.delenv("RUMI_CORS_ORIGINS", raising=False)
        monkeypatch.delenv("RUMI_PORT", raising=False)
        result = PackAPIHandler._get_cors_origin("http://localhost:9999")
        assert result == ""


class TestRateLimit:
    def test_panel_routes_bypass_rate_limit_for_loopback(self) -> None:
        handler = _make_handler(client_address=("127.0.0.1", 12345))

        with patch.object(_rate_limiter, "is_allowed", return_value=False) as mocked:
            assert handler._check_rate_limit("/api/panel/flows") is True
            mocked.assert_not_called()

    def test_panel_web_mount_bypasses_rate_limit_for_loopback(self) -> None:
        handler = _make_handler(client_address=("::1", 12345))

        with patch.object(_rate_limiter, "is_allowed", return_value=False) as mocked:
            assert handler._check_rate_limit("/panel/") is True
            mocked.assert_not_called()

    def test_non_panel_route_still_uses_rate_limit_for_loopback(self) -> None:
        handler = _make_handler(client_address=("127.0.0.1", 12345))

        with patch.object(_rate_limiter, "is_allowed", return_value=False) as mocked:
            assert handler._check_rate_limit("/api/packs") is False
            mocked.assert_called_once_with("127.0.0.1")
            handler._send_response.assert_called_once()
            response, status = handler._send_response.call_args.args
            assert response.success is False
            assert response.error == "Too Many Requests"
            assert status == 429

    def test_rate_limit_response_handles_client_disconnect(self) -> None:
        handler = _make_handler(client_address=("10.0.0.5", 12345))
        handler.close_connection = False

        def send_response(response, status=200, extra_headers=None) -> None:
            PackAPIHandler._send_response(handler, response, status, extra_headers)

        handler._send_response = send_response
        handler.end_headers.side_effect = ConnectionAbortedError(
            10053,
            "connection aborted",
        )

        with patch.object(_rate_limiter, "is_allowed", return_value=False):
            assert handler._check_rate_limit("/api/packs") is False

        assert handler.close_connection is True


# ---------------------------------------------------------------------------
# 18. PackAPIServer インスタンス化
# ---------------------------------------------------------------------------

class TestPackAPIServer:
    @patch("core_runtime.pack_api_server.get_hmac_key_manager")
    def test_init_default(self, mock_get_hmac) -> None:
        """デフォルトパラメータでインスタンス化"""
        mock_mgr = MagicMock()
        mock_mgr.get_active_key.return_value = "generated-key"
        mock_get_hmac.return_value = mock_mgr

        server = PackAPIServer(
            host="127.0.0.1",
            port=9999,
            approval_manager=MagicMock(),
            container_orchestrator=MagicMock(),
            host_privilege_manager=MagicMock(),
        )

        assert server.host == "127.0.0.1"
        assert server.port == 9999
        assert server.internal_token == "generated-key"
        assert server.server is None
        assert server.thread is None
        assert server.is_running() is False

    @patch("core_runtime.pack_api_server.get_hmac_key_manager")
    def test_init_explicit_token(self, mock_get_hmac) -> None:
        """internal_token を明示指定した場合"""
        mock_mgr = MagicMock()
        mock_get_hmac.return_value = mock_mgr

        server = PackAPIServer(
            internal_token="my-explicit-token",
        )

        assert server.internal_token == "my-explicit-token"
        mock_mgr.get_active_key.assert_not_called()

    @patch("core_runtime.pack_api_server.get_hmac_key_manager")
    def test_init_bind_address_env(self, mock_get_hmac, monkeypatch) -> None:
        """RUMI_API_BIND_ADDRESS 環境変数によるバインドアドレスオーバーライド"""
        mock_mgr = MagicMock()
        mock_mgr.get_active_key.return_value = "key"
        mock_get_hmac.return_value = mock_mgr
        monkeypatch.setenv("RUMI_API_BIND_ADDRESS", "192.168.1.1")

        server = PackAPIServer(host="127.0.0.1", port=8765)

        assert server.host == "192.168.1.1"

    @patch("core_runtime.pack_api_server.get_hmac_key_manager")
    def test_start_uses_threading_http_server_with_safe_settings(self, mock_get_hmac) -> None:
        """長いリクエストで API 全体が詰まらないよう ThreadingHTTPServer を使う。"""
        mock_get_hmac.return_value = MagicMock()
        server = PackAPIServer(host="127.0.0.1", port=0, internal_token="token")

        try:
            server.start()

            assert isinstance(server.server, ThreadingHTTPServer)
            assert server.server.allow_reuse_address is True
            assert server.server.daemon_threads is True
            assert server.server.block_on_close is False
            assert server.thread is not None
            assert server.thread.daemon is True
        finally:
            server.stop()

    @patch("core_runtime.pack_api_server.get_hmac_key_manager")
    def test_long_response_does_not_block_concurrent_get(
        self,
        mock_get_hmac,
        monkeypatch,
    ) -> None:
        """SSE 相当の長い接続中でも別 GET を処理できる。"""
        mock_get_hmac.return_value = MagicMock()
        slow_started = threading.Event()
        release_slow = threading.Event()
        slow_response = None

        def do_get(handler) -> None:
            if handler.path == "/slow":
                handler.send_response(200)
                handler.send_header("Content-Type", "text/event-stream")
                handler.end_headers()
                handler.wfile.write(b"data: start\n\n")
                handler.wfile.flush()
                slow_started.set()
                release_slow.wait(timeout=2)
                handler.wfile.write(b"data: done\n\n")
                handler.wfile.flush()
                return
            if handler.path == "/fast":
                handler.send_response(200)
                handler.end_headers()
                handler.wfile.write(b"ok")
                return
            handler.send_error(404)

        monkeypatch.setattr(PackAPIHandler, "do_GET", do_get)
        server = PackAPIServer(host="127.0.0.1", port=0, internal_token="token")

        try:
            server.start()
            assert server.server is not None
            host, port = server.server.server_address[:2]
            base_url = f"http://{host}:{port}"

            slow_response = urllib.request.urlopen(f"{base_url}/slow", timeout=2)
            assert slow_response.readline() == b"data: start\n"
            assert slow_started.wait(timeout=1)

            started = time.monotonic()
            fast_body = urllib.request.urlopen(f"{base_url}/fast", timeout=1).read()

            assert fast_body == b"ok"
            assert time.monotonic() - started < 1
        finally:
            release_slow.set()
            if slow_response is not None:
                slow_response.close()
            server.stop()


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

class TestModuleConstants:
    def test_pack_id_regex(self) -> None:
        assert PACK_ID_RE.match("valid_pack-123")
        assert not PACK_ID_RE.match("")

    def test_safe_id_regex(self) -> None:
        assert SAFE_ID_RE.match("flow:pack/step.1")
        assert not SAFE_ID_RE.match("")

    def test_max_body_bytes(self) -> None:
        assert MAX_REQUEST_BODY_BYTES == 10 * 1024 * 1024

    def test_thread_join_timeout(self) -> None:
        assert THREAD_JOIN_TIMEOUT_SECONDS == 5
