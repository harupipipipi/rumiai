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
)
from .api._helpers import _log_internal_error, _SAFE_ERROR_MSG


logger = logging.getLogger(__name__)


# --- pack_id validation (Fix #9) ---
PACK_ID_RE = re.compile(r'^[a-zA-Z0-9_-]{1,64}$')
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
    _pack_routes: dict = {}  # Pack独自ルーティングテーブル {(method, path): route_info}
    _flow_semaphore = None  # 同時実行制御用Semaphore
    
    def log_message(self, format: str, *args) -> None:
        logger.info(f"API: {args[0]}")

    @staticmethod
    def _validate_pack_id(pack_id: str) -> bool:
        """pack_id が安全なパターンに合致するか検証する (Fix #9)"""
        return bool(pack_id and PACK_ID_RE.match(pack_id))

    
    def _send_response(self, response: APIResponse, status: int = 200) -> None:
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        origin = self._get_cors_origin(self.headers.get('Origin', ''))
        if origin:
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
        self.end_headers()
        self.wfile.write(response.to_json().encode('utf-8'))
    
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
    
    def _read_raw_body(self) -> bytes:
        """リクエストボディを読み取り、インスタンスに保持して返す"""
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length == 0:
            self._raw_body_bytes = b""
            return b""
        raw = self.rfile.read(content_length)
        self._raw_body_bytes = raw
        return raw

    def _parse_body(self) -> dict:
        raw = self._read_raw_body()
        if not raw:
            return {}
        try:
            return json.loads(raw.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}
    
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
                self._send_response(APIResponse(True, result))
            
            elif path == "/api/packs/pending":
                result = self._get_pending_packs()
                self._send_response(APIResponse(True, result))
            
            elif path.startswith("/api/packs/") and path.endswith("/status"):
                pack_id = path.split("/")[3]
                if not self._validate_pack_id(pack_id):
                    self._send_response(APIResponse(False, error="Invalid pack_id"), 400)
                    return
                result = self._get_pack_status(pack_id)
                if result:
                    self._send_response(APIResponse(True, result))
                else:
                    self._send_response(APIResponse(False, error="Pack not found"), 404)
            
            elif path == "/api/containers":
                result = self._get_containers()
                self._send_response(APIResponse(True, result))
            
            elif path == "/api/privileges":
                result = self._get_privileges()
                self._send_response(APIResponse(True, result))
            
            elif path == "/api/docker/status":
                result = self._get_docker_status()
                self._send_response(APIResponse(True, result))

            elif path == "/api/network/list":
                result = self._network_list()
                self._send_response(APIResponse(True, result))

            elif path == "/api/secrets":
                result = self._secrets_list()
                self._send_response(APIResponse(True, result))

            elif path == "/api/stores":
                result = self._stores_list()
                self._send_response(APIResponse(True, result))


            elif path == "/api/stores/shared":
                result = self._stores_shared_list()
                self._send_response(APIResponse(True, result))

            elif path == "/api/units":
                query = parse_qs(urlparse(self.path).query)
                store_id = query.get("store_id", [None])[0]
                result = self._units_list(store_id)
                self._send_response(APIResponse(True, result))

            elif path == "/api/capability/blocked":
                result = self._capability_list_blocked()
                self._send_response(APIResponse(True, result))

            elif path == "/api/capability/grants":
                # GET /api/capability/grants?principal_id=xxx
                query = parse_qs(urlparse(self.path).query)
                principal_id = query.get("principal_id", [None])[0]
                result = self._capability_grants_list(principal_id)
                self._send_response(APIResponse(True, result))

            elif path == "/api/capability/requests":
                # GET /api/capability/requests?status=pending
                query = parse_qs(urlparse(self.path).query)
                status_filter = query.get("status", ["all"])[0]
                result = self._capability_list_requests(status_filter)
                self._send_response(APIResponse(True, result))

            elif path == "/api/pip/blocked":
                result = self._pip_list_blocked()
                self._send_response(APIResponse(True, result))

            elif path == "/api/pip/requests":
                # GET /api/pip/requests?status=pending
                query = parse_qs(urlparse(self.path).query)
                status_filter = query.get("status", ["all"])[0]
                result = self._pip_list_requests(status_filter)
                self._send_response(APIResponse(True, result))

            # --- Flow execution API ---
            elif path == "/api/flows":
                result = self._get_flow_list()
                self._send_response(APIResponse(True, result))

            # --- Pack custom routes (GET) ---
            elif path == "/api/routes":
                result = self._get_registered_routes()
                self._send_response(APIResponse(True, result))

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
                self._send_response(APIResponse(True, result))

            elif path == "/api/packs/import":
                source_path = body.get("path", "")
                notes = body.get("notes", "")
                if not source_path:
                    self._send_response(APIResponse(False, error="Missing 'path'"), 400)
                else:
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
                self._send_response(APIResponse(True, result))

            elif path.startswith("/api/pip/requests/") and path.endswith("/approve"):
                candidate_key = self._extract_capability_key(path, "/api/pip/requests/", "/approve")
                if candidate_key is None:
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
                if candidate_key is None:
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
                if candidate_key is None:
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
                self._send_response(APIResponse(True, result))

            elif path.startswith("/api/capability/requests/") and path.endswith("/approve"):
                candidate_key = self._extract_capability_key(path, "/api/capability/requests/", "/approve")
                if candidate_key is None:
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
                if candidate_key is None:
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
                if candidate_key is None:
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
                self._send_response(APIResponse(True, result))
            
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
                self._send_response(APIResponse(True, result))
            
            elif path.startswith("/api/privileges/") and "/grant/" in path:
                parts = path.split("/")
                pack_id = parts[3]
                privilege_id = parts[5]
                if not self._validate_pack_id(pack_id):
                    self._send_response(APIResponse(False, error="Invalid pack_id"), 400)
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
                params = body.get("params", {})
                result = self._execute_privilege(pack_id, privilege_id, params)
                if result.get("success"):
                    self._send_response(APIResponse(True, result))
                else:
                    self._send_response(APIResponse(False, error=result.get("error")), 403)

            # --- Route reload ---
            elif path == "/api/routes/reload":
                result = self._reload_pack_routes()
                self._send_response(APIResponse(True, result))

            # --- Flow execution API ---
            elif path.startswith("/api/flows/") and path.endswith("/run"):
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
                self._send_response(APIResponse(True, result))
            
            elif path.startswith("/api/packs/"):
                parts = path.strip("/").split("/")
                # Built-in: DELETE /api/packs/{pack_id} (exactly 3 segments: api/packs/{id})
                if len(parts) == 3:
                    pack_id = parts[2]
                    if not self._validate_pack_id(pack_id):
                        self._send_response(APIResponse(False, error="Invalid pack_id"), 400)
                    else:
                        result = self._uninstall_pack(pack_id)
                        self._send_response(APIResponse(True, result))
                else:
                    # Non-built-in sub-path → try Pack custom routes
                    match = self._match_pack_route(path, "DELETE")
                    if match:
                        body = self._parse_body()
                        self._handle_pack_route_request(path, body, "DELETE", match)
                    else:
                        self._send_response(APIResponse(False, error="Not found"), 404)
            
            else:
                self._send_response(APIResponse(False, error="Not found"), 404)
                
        except Exception as e:
            _log_internal_error("do_DELETE", e)
            self._send_response(APIResponse(False, error=_SAFE_ERROR_MSG), 500)
    
    # ------------------------------------------------------------------
    # Capability Handler candidate endpoints
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_capability_key(path: str, prefix: str, suffix: str) -> Optional[str]:
        """
        URL パスから candidate_key を抽出し、URL デコードする。

        例: /api/capability/requests/my_pack%3Aslug%3Aid%3Asha/approve
        → "my_pack:slug:id:sha"
        """
        if not path.startswith(prefix) or not path.endswith(suffix):
            return None
        encoded_key = path[len(prefix):-len(suffix)]
        if not encoded_key:
            return None
        return unquote(encoded_key)

    def _capability_scan(self, ecosystem_dir: Optional[str] = None) -> dict:
        try:
            from .capability_installer import get_capability_installer
            installer = get_capability_installer()
            result = installer.scan_candidates(ecosystem_dir)
            return result.to_dict()
        except Exception as e:
            _log_internal_error("capability_scan", e)
            return {"error": _SAFE_ERROR_MSG, "scanned_count": 0, "pending_created": 0}

    def _capability_list_requests(self, status_filter: str = "all") -> dict:
        try:
            from .capability_installer import get_capability_installer
            installer = get_capability_installer()
            items = installer.list_items(status_filter)
            return {"items": items, "count": len(items), "status_filter": status_filter}
        except Exception as e:
            _log_internal_error("capability_list_requests", e)
            return {"items": [], "error": _SAFE_ERROR_MSG}

    def _capability_approve(self, candidate_key: str, notes: str = "") -> dict:
        try:
            from .capability_installer import get_capability_installer
            installer = get_capability_installer()
            result = installer.approve_and_install(candidate_key, actor="api_user", notes=notes)
            return result.to_dict()
        except Exception as e:
            _log_internal_error("capability_approve", e)
            return {"success": False, "error": _SAFE_ERROR_MSG}

    def _capability_reject(self, candidate_key: str, reason: str = "") -> dict:
        try:
            from .capability_installer import get_capability_installer
            installer = get_capability_installer()
            result = installer.reject(candidate_key, actor="api_user", reason=reason)
            return result.to_dict()
        except Exception as e:
            _log_internal_error("capability_reject", e)
            return {"success": False, "error": _SAFE_ERROR_MSG}

    def _capability_list_blocked(self) -> dict:
        try:
            from .capability_installer import get_capability_installer
            installer = get_capability_installer()
            blocked = installer.list_blocked()
            return {"blocked": blocked, "count": len(blocked)}
        except Exception as e:
            _log_internal_error("capability_list_blocked", e)
            return {"blocked": {}, "error": _SAFE_ERROR_MSG}

    def _capability_unblock(self, candidate_key: str, reason: str = "") -> dict:
        try:
            from .capability_installer import get_capability_installer
            installer = get_capability_installer()
            result = installer.unblock(candidate_key, actor="api_user", reason=reason)
            return result.to_dict()
        except Exception as e:
            _log_internal_error("capability_unblock", e)
            return {"success": False, "error": _SAFE_ERROR_MSG}

    # ------------------------------------------------------------------
    # Pip dependency endpoints
    # ------------------------------------------------------------------

    def _pip_scan(self, ecosystem_dir: Optional[str] = None) -> dict:
        try:
            from .pip_installer import get_pip_installer
            installer = get_pip_installer()
            result = installer.scan_candidates(ecosystem_dir)
            return result.to_dict()
        except Exception as e:
            _log_internal_error("pip_scan", e)
            return {"error": _SAFE_ERROR_MSG, "scanned_count": 0, "pending_created": 0}

    def _pip_list_requests(self, status_filter: str = "all") -> dict:
        try:
            from .pip_installer import get_pip_installer
            installer = get_pip_installer()
            items = installer.list_items(status_filter)
            return {"items": items, "count": len(items), "status_filter": status_filter}
        except Exception as e:
            _log_internal_error("pip_list_requests", e)
            return {"items": [], "error": _SAFE_ERROR_MSG}

    def _pip_approve(self, candidate_key: str, allow_sdist: bool = False, index_url: str = "https://pypi.org/simple") -> dict:
        try:
            from .pip_installer import get_pip_installer
            installer = get_pip_installer()
            result = installer.approve_and_install(
                candidate_key, actor="api_user",
                allow_sdist=allow_sdist, index_url=index_url,
            )
            return result.to_dict()
        except Exception as e:
            _log_internal_error("pip_approve", e)
            return {"success": False, "error": _SAFE_ERROR_MSG}

    def _pip_reject(self, candidate_key: str, reason: str = "") -> dict:
        try:
            from .pip_installer import get_pip_installer
            installer = get_pip_installer()
            result = installer.reject(candidate_key, actor="api_user", reason=reason)
            return result.to_dict()
        except Exception as e:
            _log_internal_error("pip_reject", e)
            return {"success": False, "error": _SAFE_ERROR_MSG}

    def _pip_list_blocked(self) -> dict:
        try:
            from .pip_installer import get_pip_installer
            installer = get_pip_installer()
            blocked = installer.list_blocked()
            return {"blocked": blocked, "count": len(blocked)}
        except Exception as e:
            _log_internal_error("pip_list_blocked", e)
            return {"blocked": {}, "error": _SAFE_ERROR_MSG}

    def _pip_unblock(self, candidate_key: str, reason: str = "") -> dict:
        try:
            from .pip_installer import get_pip_installer
            installer = get_pip_installer()
            result = installer.unblock(candidate_key, actor="api_user", reason=reason)
            return result.to_dict()
        except Exception as e:
            _log_internal_error("pip_unblock", e)
            return {"success": False, "error": _SAFE_ERROR_MSG}

    # ------------------------------------------------------------------
    # Uninstall
    # ------------------------------------------------------------------

    def _uninstall_pack(self, pack_id: str) -> dict:
        if self.container_orchestrator:
            self.container_orchestrator.stop_container(pack_id)
            self.container_orchestrator.remove_container(pack_id)
        
        if self.approval_manager:
            self.approval_manager.remove_approval(pack_id)
        
        if self.host_privilege_manager:
            self.host_privilege_manager.revoke_all(pack_id)
        
        return {"success": True, "pack_id": pack_id}


    # ------------------------------------------------------------------
    # Flow execution API
    # ------------------------------------------------------------------

    @classmethod
    def _get_flow_semaphore(cls) -> threading.Semaphore:
        """同時実行制限用Semaphoreを取得（遅延初期化）"""
        if cls._flow_semaphore is None:
            max_concurrent = int(os.environ.get("RUMI_MAX_CONCURRENT_FLOWS", "10"))
            cls._flow_semaphore = threading.Semaphore(max_concurrent)
        return cls._flow_semaphore

    def _handle_flow_run(self, path: str, body: dict) -> None:
        """POST /api/flows/{flow_id}/run のハンドラ"""
        parts = path.split("/")
        # ["", "api", "flows", "{flow_id}", "run"]
        if len(parts) < 5:
            self._send_response(APIResponse(False, error="Invalid flow path"), 400)
            return
        flow_id = unquote(parts[3])

        if not flow_id or not flow_id.strip():
            self._send_response(APIResponse(False, error="Missing flow_id"), 400)
            return

        inputs = body.get("inputs", {})
        if not isinstance(inputs, dict):
            self._send_response(APIResponse(False, error="'inputs' must be an object"), 400)
            return

        timeout = body.get("timeout", 300)
        if not isinstance(timeout, (int, float)):
            timeout = 300
        timeout = min(max(timeout, 1), 600)

        result = self._run_flow(flow_id, inputs, timeout)
        if result.get("success"):
            self._send_response(APIResponse(True, result))
        else:
            status_code = result.get("status_code", 500)
            self._send_response(APIResponse(False, error=result.get("error")), status_code)

    def _run_flow(self, flow_id: str, inputs: dict, timeout: float) -> dict:
        """
        Flow を実行し結果を返す（共通メソッド）。
        
        Flow実行API と Pack独自ルートの両方から呼ばれる。
        """
        import time

        if self.kernel is None:
            return {"success": False, "error": "Kernel not initialized", "status_code": 503}

        # Flow 存在チェック（InterfaceRegistry 経由）
        ir = getattr(self.kernel, "interface_registry", None)
        if ir is None:
            return {"success": False, "error": "InterfaceRegistry not available", "status_code": 503}

        flow_def = ir.get(f"flow.{flow_id}", strategy="last")
        if flow_def is None:
            available = [
                k[5:] for k in (ir.list() or {}).keys()
                if k.startswith("flow.")
                and not k.startswith("flow.hooks")
                and not k.startswith("flow.construct")
            ]
            return {
                "success": False,
                "error": f"Flow '{flow_id}' not found",
                "available_flows": available,
                "status_code": 404,
            }

        # 同時実行制限
        sem = self._get_flow_semaphore()
        acquired = sem.acquire(blocking=False)
        if not acquired:
            return {
                "success": False,
                "error": "Too many concurrent flow executions. Please retry later.",
                "status_code": 429,
            }

        try:
            start_time = time.monotonic()

            ctx = self.kernel.execute_flow_sync(flow_id, inputs, timeout=timeout)

            elapsed = round(time.monotonic() - start_time, 3)

            # エラーチェック
            if isinstance(ctx, dict) and ctx.get("_error"):
                return {
                    "success": False,
                    "error": ctx["_error"],
                    "flow_id": flow_id,
                    "execution_time": elapsed,
                    "status_code": 408 if ctx.get("_flow_timeout") else 500,
                }

            # 結果から内部キーを除外
            # フィルタ方針: _ プレフィックス除外 + kernel context オブジェクト除外
            #              + callable 除外 + JSON直列化不可除外
            result_data = {}
            if isinstance(ctx, dict):
                # kernel context に注入される主要オブジェクト名のみ明示
                _ctx_object_keys = {
                    "diagnostics", "install_journal", "interface_registry",
                    "event_bus", "lifecycle", "mount_manager", "registry",
                    "active_ecosystem", "permission_manager",
                    "function_alias_registry", "flow_composer",
                    "vocab_registry", "approval_manager",
                    "container_orchestrator", "host_privilege_manager",
                    "pack_api_server",
                    "store_registry", "unit_registry",
                    "secrets_store",
                }
                result_data = {
                    k: v for k, v in ctx.items()
                    if not k.startswith("_")
                    and k not in _ctx_object_keys
                    and not callable(v)
                    and _is_json_serializable(v)
                }

            # レスポンスサイズ制限 (デフォルト 4MB)
            max_bytes = int(os.environ.get("RUMI_MAX_RESPONSE_BYTES", str(4 * 1024 * 1024)))
            try:
                result_json = json.dumps(result_data, ensure_ascii=False)
                if len(result_json.encode("utf-8")) > max_bytes:
                    logger.warning(
                        f"Flow '{flow_id}' result exceeds {max_bytes} bytes, "
                        f"truncating to keys only"
                    )
                    result_data = {
                        "_truncated": True,
                        "_reason": f"Result exceeded {max_bytes} byte limit",
                        "_keys": sorted(result_data.keys()),
                    }
            except (TypeError, ValueError):
                result_data = {"_error": "Result not JSON serializable"}

            # 監査ログ
            try:
                from .audit_logger import get_audit_logger
                audit = get_audit_logger()
                audit.log_system_event(
                    event_type="flow_api_execution",
                    success=True,
                    details={
                        "flow_id": flow_id,
                        "execution_time": elapsed,
                        "source": "api",
                    },
                )
            except Exception:
                pass

            return {
                "success": True,
                "flow_id": flow_id,
                "result": result_data,
                "execution_time": elapsed,
            }
        except Exception as e:
            _log_internal_error("run_flow", e)
            return {
                "success": False,
                "error": _SAFE_ERROR_MSG,
                "flow_id": flow_id,
                "status_code": 500,
            }
        finally:
            sem.release()

    def _get_flow_list(self) -> dict:
        """GET /api/flows — 実行可能なFlow一覧を返す"""
        if self.kernel is None:
            return {"flows": [], "error": "Kernel not initialized"}
        ir = getattr(self.kernel, "interface_registry", None)
        if ir is None:
            return {"flows": [], "error": "InterfaceRegistry not available"}
        all_keys = ir.list() or {}
        flows = [
            k[5:] for k in all_keys.keys()
            if k.startswith("flow.")
            and not k.startswith("flow.hooks")
            and not k.startswith("flow.construct")
        ]
        return {"flows": sorted(flows), "count": len(flows)}

    # ------------------------------------------------------------------
    # Pack custom route endpoints
    # ------------------------------------------------------------------

    @classmethod
    def load_pack_routes(cls, registry) -> int:
        """registryから全Packのルートを読み込み、ルーティングテーブルを構築"""
        cls._pack_routes = {}
        if registry is None:
            return 0

        try:
            all_routes = registry.get_all_routes()
        except AttributeError:
            return 0

        count = 0
        for pack_id, routes in all_routes.items():
            for route in routes:
                key = (route["method"].upper(), route["path"])
                # テンプレート解析情報を事前キャッシュ
                segments = route["path"].strip("/").split("/")
                param_indices = {}
                for i, seg in enumerate(segments):
                    if seg.startswith("{") and seg.endswith("}"):
                        param_name = seg[1:-1]
                        if re.fullmatch(r'[A-Za-z0-9_]+', param_name):
                            param_indices[i] = param_name
                cls._pack_routes[key] = {
                    "pack_id": pack_id,
                    "flow_id": route["flow_id"],
                    "timeout": route.get("timeout", 300),
                    "description": route.get("description", ""),
                    "_segments": segments,
                    "_param_indices": param_indices,
                }
                count += 1

        if count > 0:
            logger.info(f"Loaded {count} pack routes from registry")
        return count

    def _match_pack_route(self, path: str, method: str):
        """パスとメソッドがPack独自ルートにマッチするか判定。

        マッチした場合は (route_info, path_params) のタプルを返す。
        マッチしない場合は None を返す。
        {param} プレースホルダーによるパスパラメータキャプチャ対応。
        """
        method_upper = method.upper()

        # 1. 完全一致（高速パス）
        key = (method_upper, path)
        if key in self._pack_routes:
            return (self._pack_routes[key], {})

        # 2. テンプレートマッチング
        request_segments = path.strip("/").split("/")
        for (m, _template_path), route_info in self._pack_routes.items():
            if m != method_upper:
                continue
            tmpl_segments = route_info.get("_segments")
            if tmpl_segments is None:
                continue
            if len(tmpl_segments) != len(request_segments):
                continue
            param_indices = route_info.get("_param_indices", {})
            if not param_indices:
                # パラメータなしテンプレートは完全一致で既にチェック済み
                continue
            path_params = {}
            matched = True
            for i, (tmpl_seg, req_seg) in enumerate(zip(tmpl_segments, request_segments)):
                if i in param_indices:
                    path_params[param_indices[i]] = unquote(req_seg)
                elif tmpl_seg != req_seg:
                    matched = False
                    break
            if matched:
                return (route_info, path_params)

        return None

    def _handle_pack_route_request(self, path: str, body: dict, method: str,
                                   match_result: tuple = None) -> None:
        """Pack独自ルートのリクエストを処理。

        match_result: _match_pack_route() の戻り値 (route_info, path_params)。
        パスパラメータ、GETクエリパラメータ、raw body、headers を
        Flow の inputs に統合して渡す。
        """
        if match_result is None:
            self._send_response(APIResponse(False, error="Route not found"), 404)
            return

        route_info, path_params = match_result
        pack_id = route_info["pack_id"]
        flow_id = route_info["flow_id"]
        timeout = route_info["timeout"]

        # Pack承認チェック
        if self.approval_manager:
            from .approval_manager import PackStatus
            status = self.approval_manager.get_status(pack_id)
            if status != PackStatus.APPROVED:
                self._send_response(
                    APIResponse(False, error=f"Pack '{pack_id}' is not approved (status: {status})"),
                    403,
                )
                return

        # --- inputs 構築（優先順位: クエリ < body < パスパラメータ） ---
        inputs = {}

        # 1. GET クエリパラメータ
        query = parse_qs(urlparse(self.path).query)
        for k, v in query.items():
            inputs[k] = v[0] if len(v) == 1 else v

        # 2. JSON ボディ（後方互換）
        if isinstance(body, dict):
            inputs.update(body)

        # 3. パスパラメータ（最優先）
        inputs.update(path_params)

        # 4. メタデータ: raw body + headers 透過 (C3)
        raw_bytes = getattr(self, "_raw_body_bytes", b"")
        inputs["_raw_body"] = base64.b64encode(raw_bytes).decode("ascii")
        _REDACTED_HEADER_NAMES = {"authorization", "cookie", "proxy-authorization", "x-api-key"}
        inputs["_headers"] = {k.lower(): v for k, v in self.headers.items() if k.lower() not in _REDACTED_HEADER_NAMES}
        inputs["_method"] = method
        inputs["_path"] = path

        inputs["_pack_route"] = {
            "pack_id": pack_id,
            "method": method,
            "path": path,
        }

        result = self._run_flow(flow_id, inputs, timeout)
        if result.get("success"):
            self._send_response(APIResponse(True, result))
        else:
            status_code = result.get("status_code", 500)
            self._send_response(APIResponse(False, error=result.get("error")), status_code)

    def _get_registered_routes(self) -> dict:
        """GET /api/routes — 登録済みPack独自ルート一覧を返す"""
        routes = []
        for (method, path), info in self._pack_routes.items():
            routes.append({
                "method": method,
                "path": path,
                "pack_id": info["pack_id"],
                "flow_id": info["flow_id"],
                "description": info.get("description", ""),
            })
        return {"routes": routes, "count": len(routes)}


    def _reload_pack_routes(self) -> dict:
        """POST /api/routes/reload — Packルートを再読み込み"""
        try:
            from backend_core.ecosystem.registry import get_registry
            reg = get_registry()
            count = self.load_pack_routes(reg)
            logger.info(f"Pack routes reloaded: {count} routes")
            return {"reloaded": True, "route_count": count}
        except Exception as e:
            _log_internal_error("reload_pack_routes", e)
            return {"reloaded": False, "error": _SAFE_ERROR_MSG}

    # ------------------------------------------------------------------
    # Pack import/apply
    # ------------------------------------------------------------------

    def _pack_import(self, source_path: str, notes: str = "") -> dict:
        # Fix #30: restrict source_path to allowed directories
        try:
            resolved = Path(source_path).resolve()
        except (OSError, ValueError):
            return {"success": False, "error": "Invalid path"}

        allowed_roots = [Path.cwd().resolve()]
        env_paths = os.environ.get("RUMI_IMPORT_ALLOWED_PATHS", "")
        if env_paths.strip():
            for p in env_paths.split(":"):
                p = p.strip()
                if p:
                    try:
                        allowed_roots.append(Path(p).resolve())
                    except (OSError, ValueError):
                        pass

        path_allowed = False
        for root in allowed_roots:
            try:
                resolved.relative_to(root)
                path_allowed = True
                break
            except ValueError:
                continue

        if not path_allowed:
            return {"success": False, "error": "Source path is outside allowed directories"}

        try:
            from .pack_importer import get_pack_importer
            importer = get_pack_importer()
            result = importer.import_pack(source_path, notes=notes)
            return result.to_dict()
        except Exception as e:
            _log_internal_error("pack_import", e)
            return {"success": False, "error": _SAFE_ERROR_MSG}

    def _pack_apply(self, staging_id: str, mode: str = "replace") -> dict:
        try:
            from .pack_applier import get_pack_applier
            applier = get_pack_applier()
            result = applier.apply(staging_id, mode=mode)
            return result.to_dict()
        except Exception as e:
            _log_internal_error("pack_apply", e)
            return {"success": False, "error": _SAFE_ERROR_MSG}

    # ------------------------------------------------------------------
    # Secrets
    # ------------------------------------------------------------------

    def _secrets_list(self) -> dict:
        try:
            from .secrets_store import get_secrets_store
            store = get_secrets_store()
            keys = store.list_keys()
            return {"secrets": [k.to_dict() for k in keys], "count": len(keys)}
        except Exception as e:
            _log_internal_error("secrets_list", e)
            return {"secrets": [], "error": _SAFE_ERROR_MSG}

    def _secrets_set(self, body: dict) -> dict:
        key = body.get("key", "")
        value = body.get("value", "")
        if not key:
            return {"success": False, "error": "Missing 'key'"}
        if not isinstance(value, str):
            return {"success": False, "error": "'value' must be a string"}
        try:
            from .secrets_store import get_secrets_store
            store = get_secrets_store()
            result = store.set_secret(key, value)
            return result.to_dict()
        except Exception:
            return {"success": False, "error": "Failed to set secret"}

    def _secrets_delete(self, body: dict) -> dict:
        key = body.get("key", "")
        if not key:
            return {"success": False, "error": "Missing 'key'"}
        try:
            from .secrets_store import get_secrets_store
            store = get_secrets_store()
            result = store.delete_secret(key)
            return result.to_dict()
        except Exception as e:
            _log_internal_error("secrets_delete", e)
            return {"success": False, "error": _SAFE_ERROR_MSG}

    # ------------------------------------------------------------------
    # Store
    # ------------------------------------------------------------------

    def _stores_list(self) -> dict:
        try:
            from .store_registry import get_store_registry
            reg = get_store_registry()
            stores = reg.list_stores()
            return {"stores": stores, "count": len(stores)}
        except Exception as e:
            _log_internal_error("stores_list", e)
            return {"stores": [], "error": _SAFE_ERROR_MSG}

    def _stores_create(self, body: dict) -> dict:
        store_id = body.get("store_id", "")
        root_path = body.get("root_path", "")
        if not store_id or not root_path:
            return {"success": False, "error": "Missing 'store_id' or 'root_path'"}
        try:
            from .store_registry import get_store_registry
            reg = get_store_registry()
            result = reg.create_store(store_id, root_path)
            return result.to_dict()
        except Exception as e:
            _log_internal_error("stores_create", e)
            return {"success": False, "error": _SAFE_ERROR_MSG}

    # ------------------------------------------------------------------
    # Unit
    # ------------------------------------------------------------------

    def _units_list(self, store_id=None) -> dict:
        try:
            from .store_registry import get_store_registry
            from .unit_registry import get_unit_registry
            store_reg = get_store_registry()
            unit_reg = get_unit_registry()
            if store_id:
                store_def = store_reg.get_store(store_id)
                if store_def is None:
                    return {"units": [], "error": "Store not found"}
                units = unit_reg.list_units(Path(store_def.root_path))
                return {"units": [u.to_dict() for u in units], "count": len(units), "store_id": store_id}
            else:
                all_units = []
                for sd in store_reg.list_stores():
                    sid = sd.get("store_id", "")
                    rp = sd.get("root_path", "")
                    if rp:
                        units = unit_reg.list_units(Path(rp))
                        for u in units:
                            u.store_id = sid
                        all_units.extend(units)
                return {"units": [u.to_dict() for u in all_units], "count": len(all_units)}
        except Exception as e:
            _log_internal_error("units_list", e)
            return {"units": [], "error": _SAFE_ERROR_MSG}

    def _units_publish(self, body: dict) -> dict:
        store_id = body.get("store_id", "")
        source_dir = body.get("source_dir", "")
        namespace = body.get("namespace", "")
        name = body.get("name", "")
        version = body.get("version", "")
        if not all([store_id, source_dir, namespace, name, version]):
            return {"success": False, "error": "Missing required fields"}
        try:
            from .store_registry import get_store_registry
            from .unit_registry import get_unit_registry
            store_reg = get_store_registry()
            store_def = store_reg.get_store(store_id)
            if store_def is None:
                return {"success": False, "error": "Store not found"}
            unit_reg = get_unit_registry()
            result = unit_reg.publish_unit(
                Path(store_def.root_path), Path(source_dir),
                namespace, name, version, store_id=store_id,
            )
            return result.to_dict()
        except Exception as e:
            _log_internal_error("units_publish", e)
            return {"success": False, "error": _SAFE_ERROR_MSG}

    def _units_execute(self, body: dict) -> dict:
        principal_id = body.get("principal_id", "")
        unit_ref = body.get("unit_ref", {})
        mode = body.get("mode", "")
        args = body.get("args", {})
        timeout = body.get("timeout_seconds", 60.0)
        if not principal_id or not unit_ref or not mode:
            return {"success": False, "error": "Missing principal_id, unit_ref, or mode"}
        try:
            from .unit_executor import get_unit_executor
            executor = get_unit_executor()
            result = executor.execute(principal_id, unit_ref, mode, args, timeout)
            return result.to_dict()
        except Exception as e:
            _log_internal_error("units_execute", e)
            return {"success": False, "error": _SAFE_ERROR_MSG}

class PackAPIServer:
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
    return _api_server


def shutdown_pack_api_server() -> None:
    global _api_server
    if _api_server:
        _api_server.stop()
        _api_server = None
