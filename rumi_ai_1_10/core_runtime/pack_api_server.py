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
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Any, Optional
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote

from .hmac_key_manager import get_hmac_key_manager, HMACKeyManager

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
)
from .api._helpers import _log_internal_error, _SAFE_ERROR_MSG


logger = logging.getLogger(__name__)


# --- pack_id validation (Fix #9) ---
PACK_ID_RE = re.compile(r'^[a-zA-Z0-9_-]{1,64}$')
# --- 汎用 ID validation ---
SAFE_ID_RE = re.compile(r'^[a-zA-Z0-9_.:/-]{1,256}$')
# --- リクエストボディサイズ上限 (10 MB) ---
MAX_REQUEST_BODY_BYTES = 10 * 1024 * 1024
# _SAFE_ERROR_MSG: moved to api._helpers


# _log_internal_error: moved to api._helpers


@dataclass
class APIResponse:
    success: bool
    data: Any = None
    error: Optional[str] = None
    
    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


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
    BaseHTTPRequestHandler,
):
    approval_manager = None
    container_orchestrator = None
    host_privilege_manager = None
    internal_token: str = ""
    _allowed_origins: list = None
    _allowed_origins_from_env: bool = False
    _hmac_key_manager: HMACKeyManager = None
    kernel = None  # Kernel インスタンス参照（Flow実行API用）
    
    def log_message(self, format: str, *args) -> None:
        logger.info(f"API: {args[0]}")

    @staticmethod
    def _validate_pack_id(pack_id: str) -> bool:
        """pack_id が安全なパターンに合致するか検証する (Fix #9)"""
        return bool(pack_id and PACK_ID_RE.match(pack_id))

    @staticmethod
    def _is_safe_id(value: str) -> bool:
        """汎用 ID バリデーション。staging_id, privilege_id, flow_id 等に使用する。"""
        return bool(value and SAFE_ID_RE.match(value))

    
    def _send_response(self, response: APIResponse, status: int = 200) -> None:
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        origin = self._get_cors_origin(self.headers.get('Origin', ''))
        if origin:
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
        self.end_headers()
        self.wfile.write(response.to_json().encode('utf-8'))

    def _send_result(self, result, error_status: int = 500) -> None:
        """ハンドラ戻り値を判定してレスポンスを送信する (T-008)。

        戻り値が dict で ``"error"`` キーを含む場合はエラーレスポンスとして送信し、
        それ以外は成功レスポンスとして送信する。
        """
        if isinstance(result, dict) and "error" in result:
            self._send_response(
                APIResponse(False, error=result["error"]), error_status
            )
        else:
            self._send_response(APIResponse(True, data=result))
    
    def _check_auth(self) -> bool:
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
    
    def _read_raw_body(self) -> Optional[bytes]:
        """リクエストボディを読み取り、インスタンスに保持して返す。

        サイズ超過時は 413 レスポンスを送信し None を返す。

        Returns:
            bytes: 読み取ったボディ。
            None: サイズ超過（レスポンス送信済み）。
        """
        content_length = int(self.headers.get('Content-Length', 0))
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
    
    def do_OPTIONS(self) -> None:
        self.send_response(200)
        origin = self._get_cors_origin(self.headers.get('Origin', ''))
        if origin:
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Authorization, Content-Type')
        self.end_headers()

    @classmethod
    def _get_allowed_origins(cls) -> list:
        """
        許可するオリジンリストを取得。
        環境変数 RUMI_CORS_ORIGINS (カンマ区切り) でカスタマイズ可能。
        未設定の場合は localhost の特定ポート(3000,5173,8080,8765)のみ許可。
        ワイルドカードポート指定("http://localhost:*")は環境変数で
        明示的に指定した場合のみ有効。
        """
        if cls._allowed_origins is not None:
            return cls._allowed_origins

        env_origins = os.environ.get("RUMI_CORS_ORIGINS", "")
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
            cls._allowed_origins_from_env = False
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
        if not self._check_auth():
            self._send_response(APIResponse(False, error="Unauthorized"), 401)
            return
        
        parsed = urlparse(self.path)
        path = parsed.path
        
        try:
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

            elif path == "/api/stores":
                result = self._stores_list()
                self._send_result(result)


            elif path == "/api/stores/shared":
                result = self._stores_shared_list()
                self._send_result(result)

            elif path == "/api/units":
                query = parse_qs(urlparse(self.path).query)
                store_id = query.get("store_id", [None])[0]
                result = self._units_list(store_id)
                self._send_result(result)

            elif path == "/api/capability/blocked":
                result = self._capability_list_blocked()
                self._send_result(result)

            elif path == "/api/capability/grants":
                # GET /api/capability/grants?principal_id=xxx
                query = parse_qs(urlparse(self.path).query)
                principal_id = query.get("principal_id", [None])[0]
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
                    self._send_response(APIResponse(False, error="Not found"), 404)
                
        except Exception as e:
            _log_internal_error("do_GET", e)
            self._send_response(APIResponse(False, error=_SAFE_ERROR_MSG), 500)
    
    def do_POST(self) -> None:
        if not self._check_auth():
            self._send_response(APIResponse(False, error="Unauthorized"), 401)
            return
        
        try:
            body = self._parse_body()
            if body is None:
                return  # レスポンス送信済み（サイズ超過 or JSONパース失敗）
            path = urlparse(self.path).path

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
                        self._send_response(APIResponse(False, error=result.get("error", "Grant failed")), 400)

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
                        self._send_response(APIResponse(False, error=result.get("error", "Revoke failed")), 400)

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
                        self._send_response(APIResponse(False, error=result.get("error")), 400)

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
                        self._send_response(APIResponse(False, error=result.get("error")), 400)

            elif path == "/api/secrets/set":
                result = self._secrets_set(body)
                if result.get("success"):
                    self._send_response(APIResponse(True, result))
                else:
                    self._send_response(APIResponse(False, error=result.get("error")), 400)

            elif path == "/api/secrets/delete":
                result = self._secrets_delete(body)
                if result.get("success"):
                    self._send_response(APIResponse(True, result))
                else:
                    self._send_response(APIResponse(False, error=result.get("error")), 400)

            elif path == "/api/stores/create":
                result = self._stores_create(body)
                if result.get("success"):
                    self._send_response(APIResponse(True, result))
                else:
                    self._send_response(APIResponse(False, error=result.get("error")), 400)

            elif path == "/api/units/publish":
                result = self._units_publish(body)
                if result.get("success"):
                    self._send_response(APIResponse(True, result))
                else:
                    self._send_response(APIResponse(False, error=result.get("error")), 400)

            elif path == "/api/units/execute":
                result = self._units_execute(body)
                if result.get("success"):
                    self._send_response(APIResponse(True, result))
                else:
                    status_code = 403 if result.get("error_type") in (
                        "approval_denied", "grant_denied", "trust_denied"
                    ) else 400
                    self._send_response(APIResponse(False, error=result.get("error")), status_code)

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
                        self._send_response(APIResponse(False, error=result.get("error", "Approve failed")), 400)

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
                        self._send_response(APIResponse(False, error=result.get("error", "Reject failed")), 400)

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
                        self._send_response(APIResponse(False, error=result.get("error", "Unblock failed")), 400)

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
                        self._send_response(APIResponse(False, error=result.get("error", "Approve failed")), 400)

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
                        self._send_response(APIResponse(False, error=result.get("error", "Reject failed")), 400)

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
                        self._send_response(APIResponse(False, error=result.get("error", "Unblock failed")), 400)
            

            elif path == "/api/capability/grants/batch":
                grants_list = body.get("grants", [])
                result = self._capability_grants_batch(grants_list)
                if result.get("success"):
                    self._send_response(APIResponse(True, result))
                else:
                    self._send_response(APIResponse(False, error=result.get("error", "Batch grant failed")), 400)

            elif path == "/api/stores/shared/approve":
                provider_pack_id = body.get("provider_pack_id", "")
                consumer_pack_id = body.get("consumer_pack_id", "")
                store_id = body.get("store_id", "")
                result = self._stores_shared_approve(provider_pack_id, consumer_pack_id, store_id)
                if result.get("success"):
                    self._send_response(APIResponse(True, result))
                else:
                    self._send_response(APIResponse(False, error=result.get("error", "Approve failed")), 400)

            elif path == "/api/stores/shared/revoke":
                provider_pack_id = body.get("provider_pack_id", "")
                consumer_pack_id = body.get("consumer_pack_id", "")
                store_id = body.get("store_id", "")
                result = self._stores_shared_revoke(provider_pack_id, consumer_pack_id, store_id)
                if result.get("success"):
                    self._send_response(APIResponse(True, result))
                else:
                    self._send_response(APIResponse(False, error=result.get("error", "Revoke failed")), 400)

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
                        self._send_response(APIResponse(False, error=result.get("error", "Grant failed")), 400)

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
                        self._send_response(APIResponse(False, error=result.get("error", "Revoke failed")), 400)

            elif path.startswith("/api/packs/") and path.endswith("/approve"):
                pack_id = path.split("/")[3]
                if not self._validate_pack_id(pack_id):
                    self._send_response(APIResponse(False, error="Invalid pack_id"), 400)
                    return
                result = self._approve_pack(pack_id)
                if result.get("success"):
                    self._send_response(APIResponse(True, result))
                else:
                    self._send_response(APIResponse(False, error=result.get("error")), 400)
            
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
                    self._send_response(APIResponse(False, error=result.get("error")), 400)
            
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
                    self._send_response(APIResponse(False, error=result.get("error")), 400)
            
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
                    self._send_response(APIResponse(False, error=result.get("error")), 403)

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
                    self._send_response(APIResponse(False, error="Not found"), 404)
                
        except Exception as e:
            _log_internal_error("do_POST", e)
            self._send_response(APIResponse(False, error=_SAFE_ERROR_MSG), 500)
    

    def do_PUT(self) -> None:
        """PUT メソッド — Pack独自ルート専用"""
        if not self._check_auth():
            self._send_response(APIResponse(False, error="Unauthorized"), 401)
            return

        try:
            body = self._parse_body()
            if body is None:
                return  # レスポンス送信済み
            path = urlparse(self.path).path

            match = self._match_pack_route(path, "PUT")
            if match:
                self._handle_pack_route_request(path, body, "PUT", match)
            else:
                self._send_response(APIResponse(False, error="Not found"), 404)

        except Exception as e:
            _log_internal_error("do_PUT", e)
            self._send_response(APIResponse(False, error=_SAFE_ERROR_MSG), 500)

    def do_DELETE(self) -> None:
        if not self._check_auth():
            self._send_response(APIResponse(False, error="Unauthorized"), 401)
            return
        
        path = urlparse(self.path).path
        
        try:
            if path.startswith("/api/containers/"):
                pack_id = path.split("/")[3]
                if not self._validate_pack_id(pack_id):
                    self._send_response(APIResponse(False, error="Invalid pack_id"), 400)
                    return
                result = self._remove_container(pack_id)
                self._send_result(result)
            
            elif path.startswith("/api/packs/"):
                parts = path.strip("/").split("/")
                # Built-in: DELETE /api/packs/{pack_id} (exactly 3 segments: api/packs/{id})
                if len(parts) == 3:
                    pack_id = parts[2]
                    if not self._validate_pack_id(pack_id):
                        self._send_response(APIResponse(False, error="Invalid pack_id"), 400)
                    else:
                        result = self._uninstall_pack(pack_id)
                        self._send_result(result)
                else:
                    # Non-built-in sub-path → try Pack custom routes
                    match = self._match_pack_route(path, "DELETE")
                    if match:
                        body = self._parse_body()
                        if body is None:
                            return  # レスポンス送信済み
                        self._handle_pack_route_request(path, body, "DELETE", match)
                    else:
                        self._send_response(APIResponse(False, error="Not found"), 404)
            
            else:
                # T-009: Pack独自ルートフォールバック追加
                match = self._match_pack_route(path, "DELETE")
                if match:
                    body = self._parse_body()
                    if body is None:
                        return  # レスポンス送信済み
                    self._handle_pack_route_request(path, body, "DELETE", match)
                else:
                    self._send_response(APIResponse(False, error="Not found"), 404)
                
        except Exception as e:
            _log_internal_error("do_DELETE", e)
            self._send_response(APIResponse(False, error=_SAFE_ERROR_MSG), 500)
    
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        approval_manager = None,
        container_orchestrator = None,
        host_privilege_manager = None,
        internal_token: str = None,
        kernel = None
    ):
        self.kernel = kernel
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
        
        if internal_token is None:
            # HMACKeyManager からアクティブ鍵を取得
            internal_token = self._hmac_key_manager.get_active_key()
            logger.info("Using HMAC-managed API token: [REDACTED]")
            logger.warning("Set this token in client requests: Authorization: Bearer <token>")
            logger.warning("Token rotation: set RUMI_HMAC_ROTATE=true and restart")
        
        self.internal_token = internal_token
        self.server: Optional[HTTPServer] = None
        self.thread: Optional[threading.Thread] = None
    
    def start(self) -> None:
        PackAPIHandler.approval_manager = self.approval_manager
        PackAPIHandler.container_orchestrator = self.container_orchestrator
        PackAPIHandler.host_privilege_manager = self.host_privilege_manager
        PackAPIHandler.internal_token = self.internal_token
        PackAPIHandler._hmac_key_manager = self._hmac_key_manager
        PackAPIHandler.kernel = self.kernel

        # Packルートをregistryから読み込み
        try:
            from backend_core.ecosystem.registry import get_registry
            reg = get_registry()
            PackAPIHandler.load_pack_routes(reg)
        except Exception as e:
            logger.warning(f"Failed to load pack routes: {e}")
        
        self.server = HTTPServer((self.host, self.port), PackAPIHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        logger.info(f"Pack API server started on http://{self.host}:{self.port}")
    
    def stop(self) -> None:
        if self.server:
            self.server.shutdown()
            self.server = None
        if self.thread:
            self.thread.join(timeout=5)
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
    internal_token: str = None,
    kernel = None
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
        kernel=kernel
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
