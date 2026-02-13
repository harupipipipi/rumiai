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
import secrets
import threading
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Any, Optional
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote

from .hmac_key_manager import get_hmac_key_manager, HMACKeyManager


logger = logging.getLogger(__name__)


@dataclass
class APIResponse:
    success: bool
    data: Any = None
    error: Optional[str] = None
    
    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


class PackAPIHandler(BaseHTTPRequestHandler):
    approval_manager = None
    container_orchestrator = None
    host_privilege_manager = None
    internal_token: str = ""
    _allowed_origins: list = None
    _hmac_key_manager: HMACKeyManager = None
    kernel = None  # Kernel インスタンス参照（Flow実行API用）
    _pack_routes: dict = {}  # Pack独自ルーティングテーブル {(method, path): route_info}
    _flow_semaphore = None  # 同時実行制御用Semaphore
    
    def log_message(self, format: str, *args) -> None:
        logger.info(f"API: {args[0]}")
    
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
    
    def _parse_body(self) -> dict:
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length == 0:
            return {}
        body = self.rfile.read(content_length)
        return json.loads(body.decode('utf-8'))
    
    def do_OPTIONS(self) -> None:
        self.send_response(200)
        origin = self._get_cors_origin(self.headers.get('Origin', ''))
        if origin:
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Authorization, Content-Type')
        self.end_headers()

    @classmethod
    def _get_allowed_origins(cls) -> list:
        """
        許可するオリジンリストを取得。
        環境変数 RUMI_CORS_ORIGINS (カンマ区切り) でカスタマイズ可能。
        未設定の場合は localhost 系のみ許可（安全なデフォルト）。
        ワイルドカードポート指定: "http://localhost:*"
        """
        if cls._allowed_origins is not None:
            return cls._allowed_origins

        env_origins = os.environ.get("RUMI_CORS_ORIGINS", "")
        if env_origins.strip():
            cls._allowed_origins = [o.strip() for o in env_origins.split(",") if o.strip()]
        else:
            cls._allowed_origins = [
                "http://localhost:*",
                "http://127.0.0.1:*",
            ]
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
            # "http://localhost:*" — ワイルドカードポート対応
            if pattern.endswith(":*"):
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

            elif self._match_pack_route(path, "GET"):
                self._handle_pack_route_request(path, {}, "GET")
            
            else:
                self._send_response(APIResponse(False, error="Not found"), 404)
                
        except Exception as e:
            logger.exception(f"API error: {e}")
            self._send_response(APIResponse(False, error=str(e)), 500)
    
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
                result = self._approve_pack(pack_id)
                if result.get("success"):
                    self._send_response(APIResponse(True, result))
                else:
                    self._send_response(APIResponse(False, error=result.get("error")), 400)
            
            elif path.startswith("/api/packs/") and path.endswith("/reject"):
                pack_id = path.split("/")[3]
                reason = body.get("reason", "User rejected")
                result = self._reject_pack(pack_id, reason)
                self._send_response(APIResponse(True, result))
            
            elif path.startswith("/api/containers/") and path.endswith("/start"):
                pack_id = path.split("/")[3]
                result = self._start_container(pack_id)
                if result.get("success"):
                    self._send_response(APIResponse(True, result))
                else:
                    self._send_response(APIResponse(False, error=result.get("error")), 400)
            
            elif path.startswith("/api/containers/") and path.endswith("/stop"):
                pack_id = path.split("/")[3]
                result = self._stop_container(pack_id)
                self._send_response(APIResponse(True, result))
            
            elif path.startswith("/api/privileges/") and "/grant/" in path:
                parts = path.split("/")
                pack_id = parts[3]
                privilege_id = parts[5]
                result = self._grant_privilege(pack_id, privilege_id)
                if result.get("success"):
                    self._send_response(APIResponse(True, result))
                else:
                    self._send_response(APIResponse(False, error=result.get("error")), 400)
            
            elif path.startswith("/api/privileges/") and "/execute/" in path:
                parts = path.split("/")
                pack_id = parts[3]
                privilege_id = parts[5]
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
            elif self._match_pack_route(path, "POST"):
                self._handle_pack_route_request(path, body, "POST")
            
            else:
                self._send_response(APIResponse(False, error="Not found"), 404)
                
        except Exception as e:
            logger.exception(f"API error: {e}")
            self._send_response(APIResponse(False, error=str(e)), 500)
    

    def do_PUT(self) -> None:
        """PUT メソッド — Pack独自ルート専用"""
        if not self._check_auth():
            self._send_response(APIResponse(False, error="Unauthorized"), 401)
            return

        try:
            body = self._parse_body()
            path = urlparse(self.path).path

            if self._match_pack_route(path, "PUT"):
                self._handle_pack_route_request(path, body, "PUT")
            else:
                self._send_response(APIResponse(False, error="Not found"), 404)

        except Exception as e:
            logger.exception(f"API error: {e}")
            self._send_response(APIResponse(False, error=str(e)), 500)

    def do_DELETE(self) -> None:
        if not self._check_auth():
            self._send_response(APIResponse(False, error="Unauthorized"), 401)
            return
        
        path = urlparse(self.path).path
        
        try:
            if path.startswith("/api/containers/"):
                pack_id = path.split("/")[3]
                result = self._remove_container(pack_id)
                self._send_response(APIResponse(True, result))
            
            elif path.startswith("/api/packs/"):
                # Pack独自ルート (DELETE) を先にチェック
                if self._match_pack_route(path, "DELETE"):
                    body = self._parse_body()
                    self._handle_pack_route_request(path, body, "DELETE")
                else:
                    pack_id = path.split("/")[3]
                    result = self._uninstall_pack(pack_id)
                    self._send_response(APIResponse(True, result))
            
            else:
                self._send_response(APIResponse(False, error="Not found"), 404)
                
        except Exception as e:
            logger.exception(f"API error: {e}")
            self._send_response(APIResponse(False, error=str(e)), 500)
    
    # ------------------------------------------------------------------
    # Pack endpoints
    # ------------------------------------------------------------------

    def _get_all_packs(self) -> list:
        if not self.approval_manager:
            return []
        packs = self.approval_manager.scan_packs()
        return [
            {
                "pack_id": p,
                "status": self.approval_manager.get_status(p).value if self.approval_manager.get_status(p) else "unknown"
            }
            for p in packs
        ]
    
    def _get_pending_packs(self) -> list:
        if not self.approval_manager:
            return []
        return self.approval_manager.get_pending_packs()
    
    def _get_pack_status(self, pack_id: str) -> Optional[dict]:
        if not self.approval_manager:
            return None
        status = self.approval_manager.get_status(pack_id)
        if not status:
            return None
        approval = self.approval_manager.get_approval(pack_id)
        return {
            "pack_id": pack_id,
            "status": status.value,
            "approval": asdict(approval) if approval else None
        }
    
    def _scan_packs(self) -> dict:
        if not self.approval_manager:
            return {"scanned": 0}
        packs = self.approval_manager.scan_packs()
        return {"scanned": len(packs), "packs": packs}
    
    def _approve_pack(self, pack_id: str) -> dict:
        if not self.approval_manager:
            return {"success": False, "error": "ApprovalManager not initialized"}
        result = self.approval_manager.approve(pack_id)
        return {"success": result.success, "error": result.error}
    
    def _reject_pack(self, pack_id: str, reason: str) -> dict:
        if not self.approval_manager:
            return {"success": False}
        self.approval_manager.reject(pack_id, reason)
        return {"success": True, "pack_id": pack_id, "reason": reason}
    
    # ------------------------------------------------------------------
    # Container endpoints
    # ------------------------------------------------------------------

    def _get_containers(self) -> list:
        if not self.container_orchestrator:
            return []
        return self.container_orchestrator.list_containers()
    
    def _start_container(self, pack_id: str) -> dict:
        if not self.container_orchestrator:
            return {"success": False, "error": "ContainerOrchestrator not initialized"}
        
        if self.approval_manager:
            from .approval_manager import PackStatus
            status = self.approval_manager.get_status(pack_id)
            if status != PackStatus.APPROVED:
                return {"success": False, "error": f"Pack not approved: {status}"}
        
        result = self.container_orchestrator.start_container(pack_id)
        return {"success": result.success, "container_id": result.container_id, "error": result.error}
    
    def _stop_container(self, pack_id: str) -> dict:
        if not self.container_orchestrator:
            return {"success": False}
        result = self.container_orchestrator.stop_container(pack_id)
        return {"success": result.success}
    
    def _remove_container(self, pack_id: str) -> dict:
        if not self.container_orchestrator:
            return {"success": False}
        self.container_orchestrator.stop_container(pack_id)
        self.container_orchestrator.remove_container(pack_id)
        return {"success": True, "pack_id": pack_id}

    # ------------------------------------------------------------------
    # Network Grant endpoints (B-2)
    # ------------------------------------------------------------------

    def _network_grant(self, pack_id: str, allowed_domains: list, allowed_ports: list,
                       granted_by: str = "api_user", notes: str = "") -> dict:
        try:
            from .network_grant_manager import get_network_grant_manager
            ngm = get_network_grant_manager()
            grant = ngm.grant_network_access(
                pack_id=pack_id,
                allowed_domains=allowed_domains,
                allowed_ports=allowed_ports,
                granted_by=granted_by,
                notes=notes,
            )
            return {"success": True, "pack_id": pack_id, "grant": grant.to_dict()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _network_revoke(self, pack_id: str, reason: str = "") -> dict:
        try:
            from .network_grant_manager import get_network_grant_manager
            ngm = get_network_grant_manager()
            success = ngm.revoke_network_access(pack_id=pack_id, reason=reason)
            return {"success": success, "pack_id": pack_id, "revoked": success}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _network_check(self, pack_id: str, domain: str, port: int) -> dict:
        try:
            from .network_grant_manager import get_network_grant_manager
            ngm = get_network_grant_manager()
            result = ngm.check_access(pack_id, domain, port)
            return {
                "allowed": result.allowed,
                "reason": result.reason,
                "pack_id": result.pack_id,
                "domain": result.domain,
                "port": result.port,
            }
        except Exception as e:
            return {"allowed": False, "error": str(e)}

    def _network_list(self) -> dict:
        try:
            from .network_grant_manager import get_network_grant_manager
            ngm = get_network_grant_manager()
            grants = ngm.get_all_grants()
            disabled = ngm.get_disabled_packs()
            return {
                "grants": {k: v.to_dict() for k, v in grants.items()},
                "grant_count": len(grants),
                "disabled_packs": list(disabled),
                "disabled_count": len(disabled),
            }
        except Exception as e:
            return {"grants": {}, "error": str(e)}

    # ------------------------------------------------------------------
    # Capability Grant endpoints (G-1)
    # ------------------------------------------------------------------

    def _capability_grants_grant(self, principal_id: str, permission_id: str, config=None) -> dict:
        try:
            from .capability_grant_manager import get_capability_grant_manager
            gm = get_capability_grant_manager()
            gm.grant_permission(principal_id, permission_id, config)
            try:
                from .audit_logger import get_audit_logger
                audit = get_audit_logger()
                audit.log_permission_event(
                    pack_id=principal_id,
                    permission_type="capability_grant",
                    action="grant",
                    success=True,
                    details={
                        "principal_id": principal_id,
                        "permission_id": permission_id,
                        "has_config": config is not None,
                        "source": "api",
                    },
                )
            except Exception:
                pass
            return {"success": True, "principal_id": principal_id, "permission_id": permission_id, "granted": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _capability_grants_revoke(self, principal_id: str, permission_id: str) -> dict:
        try:
            from .capability_grant_manager import get_capability_grant_manager
            gm = get_capability_grant_manager()
            gm.revoke_permission(principal_id, permission_id)
            try:
                from .audit_logger import get_audit_logger
                audit = get_audit_logger()
                audit.log_permission_event(
                    pack_id=principal_id,
                    permission_type="capability_grant",
                    action="revoke",
                    success=True,
                    details={
                        "principal_id": principal_id,
                        "permission_id": permission_id,
                        "source": "api",
                    },
                )
            except Exception:
                pass
            return {"success": True, "principal_id": principal_id, "permission_id": permission_id, "revoked": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _capability_grants_list(self, principal_id: str = None) -> dict:
        try:
            from .capability_grant_manager import get_capability_grant_manager
            gm = get_capability_grant_manager()
            if principal_id:
                grant = gm.get_grant(principal_id)
                if grant is None:
                    return {"grants": {}, "count": 0, "principal_id": principal_id}
                g_dict = grant.to_dict() if hasattr(grant, "to_dict") else grant
                return {"grants": {principal_id: g_dict}, "count": 1, "principal_id": principal_id}
            else:
                all_grants = gm.get_all_grants()
                result = {}
                for pid, g in all_grants.items():
                    result[pid] = g.to_dict() if hasattr(g, "to_dict") else g
                return {"grants": result, "count": len(result)}
        except Exception as e:
            return {"grants": {}, "error": str(e)}
    
    # ------------------------------------------------------------------
    # Privilege endpoints
    # ------------------------------------------------------------------

    def _get_privileges(self) -> list:
        if not self.host_privilege_manager:
            return []
        return self.host_privilege_manager.list_privileges()
    
    def _grant_privilege(self, pack_id: str, privilege_id: str) -> dict:
        if not self.host_privilege_manager:
            return {"success": False, "error": "HostPrivilegeManager not initialized"}
        result = self.host_privilege_manager.grant(pack_id, privilege_id)
        return {"success": result.success, "error": result.error}
    
    def _execute_privilege(self, pack_id: str, privilege_id: str, params: dict) -> dict:
        if not self.host_privilege_manager:
            return {"success": False, "error": "HostPrivilegeManager not initialized"}
        result = self.host_privilege_manager.execute(pack_id, privilege_id, params)
        return {"success": result.success, "result": result.data, "error": result.error}
    
    # ------------------------------------------------------------------
    # Docker status
    # ------------------------------------------------------------------

    def _get_docker_status(self) -> dict:
        if self.container_orchestrator:
            available = self.container_orchestrator.is_docker_available()
        else:
            import subprocess
            try:
                subprocess.run(["docker", "info"], capture_output=True, check=True, timeout=5)
                available = True
            except:
                available = False
        
        return {"available": available, "required": True}
    
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
            return {"error": str(e), "scanned_count": 0, "pending_created": 0}

    def _capability_list_requests(self, status_filter: str = "all") -> dict:
        try:
            from .capability_installer import get_capability_installer
            installer = get_capability_installer()
            items = installer.list_items(status_filter)
            return {"items": items, "count": len(items), "status_filter": status_filter}
        except Exception as e:
            return {"items": [], "error": str(e)}

    def _capability_approve(self, candidate_key: str, notes: str = "") -> dict:
        try:
            from .capability_installer import get_capability_installer
            installer = get_capability_installer()
            result = installer.approve_and_install(candidate_key, actor="api_user", notes=notes)
            return result.to_dict()
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _capability_reject(self, candidate_key: str, reason: str = "") -> dict:
        try:
            from .capability_installer import get_capability_installer
            installer = get_capability_installer()
            result = installer.reject(candidate_key, actor="api_user", reason=reason)
            return result.to_dict()
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _capability_list_blocked(self) -> dict:
        try:
            from .capability_installer import get_capability_installer
            installer = get_capability_installer()
            blocked = installer.list_blocked()
            return {"blocked": blocked, "count": len(blocked)}
        except Exception as e:
            return {"blocked": {}, "error": str(e)}

    def _capability_unblock(self, candidate_key: str, reason: str = "") -> dict:
        try:
            from .capability_installer import get_capability_installer
            installer = get_capability_installer()
            result = installer.unblock(candidate_key, actor="api_user", reason=reason)
            return result.to_dict()
        except Exception as e:
            return {"success": False, "error": str(e)}

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
            return {"error": str(e), "scanned_count": 0, "pending_created": 0}

    def _pip_list_requests(self, status_filter: str = "all") -> dict:
        try:
            from .pip_installer import get_pip_installer
            installer = get_pip_installer()
            items = installer.list_items(status_filter)
            return {"items": items, "count": len(items), "status_filter": status_filter}
        except Exception as e:
            return {"items": [], "error": str(e)}

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
            return {"success": False, "error": str(e)}

    def _pip_reject(self, candidate_key: str, reason: str = "") -> dict:
        try:
            from .pip_installer import get_pip_installer
            installer = get_pip_installer()
            result = installer.reject(candidate_key, actor="api_user", reason=reason)
            return result.to_dict()
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _pip_list_blocked(self) -> dict:
        try:
            from .pip_installer import get_pip_installer
            installer = get_pip_installer()
            blocked = installer.list_blocked()
            return {"blocked": blocked, "count": len(blocked)}
        except Exception as e:
            return {"blocked": {}, "error": str(e)}

    def _pip_unblock(self, candidate_key: str, reason: str = "") -> dict:
        try:
            from .pip_installer import get_pip_installer
            installer = get_pip_installer()
            result = installer.unblock(candidate_key, actor="api_user", reason=reason)
            return result.to_dict()
        except Exception as e:
            return {"success": False, "error": str(e)}

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
            logger.exception(f"Flow execution error: {e}")
            return {
                "success": False,
                "error": str(e),
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
                cls._pack_routes[key] = {
                    "pack_id": pack_id,
                    "flow_id": route["flow_id"],
                    "timeout": route.get("timeout", 300),
                    "description": route.get("description", ""),
                }
                count += 1

        if count > 0:
            logger.info(f"Loaded {count} pack routes from registry")
        return count

    def _match_pack_route(self, path: str, method: str) -> bool:
        """パスとメソッドがPack独自ルートにマッチするか判定"""
        return (method.upper(), path) in self._pack_routes

    def _handle_pack_route_request(self, path: str, body: dict, method: str) -> None:
        """Pack独自ルートのリクエストを処理"""
        route_info = self._pack_routes.get((method.upper(), path))
        if not route_info:
            self._send_response(APIResponse(False, error="Route not found"), 404)
            return

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

        # Flow実行（共通の _run_flow を使用）
        inputs = body if isinstance(body, dict) else {}
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
            logger.exception(f"Failed to reload pack routes: {e}")
            return {"reloaded": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Pack import/apply
    # ------------------------------------------------------------------

    def _pack_import(self, source_path: str, notes: str = "") -> dict:
        try:
            from .pack_importer import get_pack_importer
            importer = get_pack_importer()
            result = importer.import_pack(source_path, notes=notes)
            return result.to_dict()
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _pack_apply(self, staging_id: str, mode: str = "replace") -> dict:
        try:
            from .pack_applier import get_pack_applier
            applier = get_pack_applier()
            result = applier.apply(staging_id, mode=mode)
            return result.to_dict()
        except Exception as e:
            return {"success": False, "error": str(e)}

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
            return {"secrets": [], "error": str(e)}

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
            return {"success": False, "error": str(e)}

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
            return {"stores": [], "error": str(e)}

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
            return {"success": False, "error": str(e)}

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
                    return {"units": [], "error": f"Store not found: {store_id}"}
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
            return {"units": [], "error": str(e)}

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
                return {"success": False, "error": f"Store not found: {store_id}"}
            unit_reg = get_unit_registry()
            result = unit_reg.publish_unit(
                Path(store_def.root_path), Path(source_dir),
                namespace, name, version, store_id=store_id,
            )
            return result.to_dict()
        except Exception as e:
            return {"success": False, "error": str(e)}

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
            return {"success": False, "error": str(e)}

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
        self.host = host
        self.port = port
        self.approval_manager = approval_manager
        self.container_orchestrator = container_orchestrator
        self.host_privilege_manager = host_privilege_manager
        
        # HMAC鍵管理: HMACKeyManager を使用
        self._hmac_key_manager = get_hmac_key_manager()
        
        if internal_token is None:
            # HMACKeyManager からアクティブ鍵を取得
            internal_token = self._hmac_key_manager.get_active_key()
            logger.warning(f"Using HMAC-managed API token: {internal_token}")
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
