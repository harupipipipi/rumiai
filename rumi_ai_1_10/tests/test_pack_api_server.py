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
from email.message import Message
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from core_runtime.pack_api_server import (
    PackAPIHandler,
    PackAPIServer,
    PACK_ID_RE,
    SAFE_ID_RE,
    MAX_REQUEST_BODY_BYTES,
    THREAD_JOIN_TIMEOUT_SECONDS,
)
from core_runtime.api.api_response import APIResponse


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


# ---------------------------------------------------------------------------
# 5-9. 認証 (_check_auth)
# ---------------------------------------------------------------------------

class TestCheckAuth:
    def test_auth_success_hmac_manager(self) -> None:
        """HMACKeyManager.verify_token が True を返す → 認証成功"""
        mock_mgr = MagicMock()
        mock_mgr.verify_token.return_value = True
        handler = _make_handler(
            headers=_make_headers(Authorization="Bearer my-secret-token"),
            _hmac_key_manager=mock_mgr,
        )
        assert handler._check_auth() is True
        mock_mgr.verify_token.assert_called_once_with("my-secret-token")

    def test_auth_failure_no_header(self) -> None:
        """Authorization ヘッダーなし → 認証失敗"""
        handler = _make_handler(headers=_make_headers())
        assert handler._check_auth() is False

    def test_auth_failure_no_bearer_prefix(self) -> None:
        """Bearer プレフィックスなし → 認証失敗"""
        handler = _make_handler(
            headers=_make_headers(Authorization="Basic abc123"),
        )
        assert handler._check_auth() is False

    def test_auth_fallback_internal_token_success(self) -> None:
        """HMACKeyManager=None, internal_token で一致 → 成功"""
        handler = _make_handler(
            headers=_make_headers(Authorization="Bearer fallback-token"),
            _hmac_key_manager=None,
            internal_token="fallback-token",
        )
        assert handler._check_auth() is True

    def test_auth_fallback_internal_token_mismatch(self) -> None:
        """HMACKeyManager=None, internal_token 不一致 → 失敗"""
        handler = _make_handler(
            headers=_make_headers(Authorization="Bearer wrong-token"),
            _hmac_key_manager=None,
            internal_token="correct-token",
        )
        assert handler._check_auth() is False

    def test_auth_fallback_no_internal_token_configured(self) -> None:
        """HMACKeyManager=None, internal_token="" → 失敗"""
        handler = _make_handler(
            headers=_make_headers(Authorization="Bearer some-token"),
            _hmac_key_manager=None,
            internal_token="",
        )
        assert handler._check_auth() is False


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
        yield
        PackAPIHandler._allowed_origins = None
        PackAPIHandler._allowed_origins_from_env = False

    def test_cors_allowed_default(self, monkeypatch) -> None:
        """デフォルト許可リストに含まれるオリジン → 返却"""
        monkeypatch.delenv("RUMI_CORS_ORIGINS", raising=False)
        result = PackAPIHandler._get_cors_origin("http://localhost:3000")
        assert result == "http://localhost:3000"

    def test_cors_disallowed_origin(self, monkeypatch) -> None:
        """デフォルト許可リストに含まれないオリジン → 空文字"""
        monkeypatch.delenv("RUMI_CORS_ORIGINS", raising=False)
        result = PackAPIHandler._get_cors_origin("http://evil.com")
        assert result == ""

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
        result = PackAPIHandler._get_cors_origin("http://localhost:9999")
        assert result == ""


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
