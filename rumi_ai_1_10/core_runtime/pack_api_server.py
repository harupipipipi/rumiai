"""
pack_api_server.py - Pack管理HTTP APIサーバー

Pack承認、コンテナ操作、特権操作のHTTP APIを提供。
"""

from __future__ import annotations

import hmac
import json
import logging
import secrets
import threading
from dataclasses import dataclass, asdict
from typing import Any, Optional
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs


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
    
    def log_message(self, format: str, *args) -> None:
        logger.info(f"API: {args[0]}")
    
    def _send_response(self, response: APIResponse, status: int = 200) -> None:
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(response.to_json().encode('utf-8'))
    
    def _check_auth(self) -> bool:
        auth_header = self.headers.get('Authorization', '')
        
        if not self.internal_token:
            logger.error("API token not configured - rejecting request")
            return False
        
        if not auth_header:
            return False
        
        return hmac.compare_digest(auth_header, f"Bearer {self.internal_token}")
    
    def _parse_body(self) -> dict:
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length == 0:
            return {}
        body = self.rfile.read(content_length)
        return json.loads(body.decode('utf-8'))
    
    def do_OPTIONS(self) -> None:
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Authorization, Content-Type')
        self.end_headers()
    
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
            
            else:
                self._send_response(APIResponse(False, error="Not found"), 404)
                
        except Exception as e:
            logger.exception(f"API error: {e}")
            self._send_response(APIResponse(False, error=str(e)), 500)
    
    def do_POST(self) -> None:
        if not self._check_auth():
            self._send_response(APIResponse(False, error="Unauthorized"), 401)
            return
        
        path = urlparse(self.path).path
        
        try:
            body = self._parse_body()
            
            if path == "/api/packs/scan":
                result = self._scan_packs()
                self._send_response(APIResponse(True, result))
            
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
                pack_id = path.split("/")[3]
                result = self._uninstall_pack(pack_id)
                self._send_response(APIResponse(True, result))
            
            else:
                self._send_response(APIResponse(False, error="Not found"), 404)
                
        except Exception as e:
            logger.exception(f"API error: {e}")
            self._send_response(APIResponse(False, error=str(e)), 500)
    
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
    
    def _uninstall_pack(self, pack_id: str) -> dict:
        if self.container_orchestrator:
            self.container_orchestrator.stop_container(pack_id)
            self.container_orchestrator.remove_container(pack_id)
        
        if self.approval_manager:
            self.approval_manager.remove_approval(pack_id)
        
        if self.host_privilege_manager:
            self.host_privilege_manager.revoke_all(pack_id)
        
        return {"success": True, "pack_id": pack_id}


class PackAPIServer:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        approval_manager = None,
        container_orchestrator = None,
        host_privilege_manager = None,
        internal_token: str = None
    ):
        self.host = host
        self.port = port
        self.approval_manager = approval_manager
        self.container_orchestrator = container_orchestrator
        self.host_privilege_manager = host_privilege_manager
        
        if internal_token is None:
            internal_token = secrets.token_urlsafe(32)
            logger.warning(f"Generated API token: {internal_token}")
            logger.warning("Set this token in client requests: Authorization: Bearer <token>")
        
        self.internal_token = internal_token
        self.server: Optional[HTTPServer] = None
        self.thread: Optional[threading.Thread] = None
    
    def start(self) -> None:
        PackAPIHandler.approval_manager = self.approval_manager
        PackAPIHandler.container_orchestrator = self.container_orchestrator
        PackAPIHandler.host_privilege_manager = self.host_privilege_manager
        PackAPIHandler.internal_token = self.internal_token
        
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
    internal_token: str = None
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
        internal_token=internal_token
    )
    _api_server.start()
    return _api_server


def shutdown_pack_api_server() -> None:
    global _api_server
    if _api_server:
        _api_server.stop()
        _api_server = None
