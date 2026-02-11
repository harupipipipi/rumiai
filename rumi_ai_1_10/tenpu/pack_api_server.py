"""
pack_api_server.py - Pack管理HTTP APIサーバー

Pack承認、コンテナ操作、特権操作、Capability Handler候補管理、
pip依存ライブラリ管理のHTTP APIを提供。
"""

from __future__ import annotations

import hmac
import json
import logging
import secrets
import threading
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Any, Optional
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote


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
