"""
egress_proxy.py - Egress Proxy サーバー

Packからの外部ネットワーク通信を仲介するプロキシサーバー。
network grant に基づいて allow/deny を判定し、監査ログに記録する。
"""

from __future__ import annotations

import json
import socket
import ssl
import threading
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse


@dataclass
class ProxyRequest:
    """プロキシリクエスト"""
    owner_pack: str
    method: str
    url: str
    headers: Dict[str, str]
    body: Optional[bytes]
    timeout_seconds: float = 30.0
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProxyRequest':
        return cls(
            owner_pack=data.get("owner_pack", ""),
            method=data.get("method", "GET").upper(),
            url=data.get("url", ""),
            headers=data.get("headers", {}),
            body=data.get("body", "").encode("utf-8") if data.get("body") else None,
            timeout_seconds=data.get("timeout_seconds", 30.0),
        )


@dataclass
class ProxyResponse:
    """プロキシレスポンス"""
    success: bool
    status_code: int = 0
    headers: Dict[str, str] = field(default_factory=dict)
    body: str = ""
    error: Optional[str] = None
    error_type: Optional[str] = None
    allowed: bool = True
    rejection_reason: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        d = {
            "success": self.success,
            "status_code": self.status_code,
            "headers": self.headers,
            "body": self.body,
            "allowed": self.allowed,
        }
        if self.error:
            d["error"] = self.error
            d["error_type"] = self.error_type
        if self.rejection_reason:
            d["rejection_reason"] = self.rejection_reason
        return d


class EgressHTTPServer(HTTPServer):
    """カスタムHTTPServer（インスタンス変数でマネージャを保持）"""
    
    def __init__(self, server_address, RequestHandlerClass, network_grant_manager=None, audit_logger=None):
        super().__init__(server_address, RequestHandlerClass)
        self.network_grant_manager = network_grant_manager
        self.audit_logger = audit_logger
        self.allowed_internal_ips = ["127.0.0.1", "::1", "localhost"]


class EgressProxyHandler(BaseHTTPRequestHandler):
    """HTTPリクエストハンドラ"""
    
    def log_message(self, format: str, *args) -> None:
        pass
    
    @property
    def network_grant_manager(self):
        return self.server.network_grant_manager
    
    @property
    def audit_logger(self):
        return self.server.audit_logger
    
    @property
    def allowed_internal_ips(self):
        return self.server.allowed_internal_ips
    
    def _send_json_response(self, status_code: int, data: Dict[str, Any]) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)
    
    def _check_client_allowed(self) -> bool:
        client_ip = self.client_address[0]
        return client_ip in self.allowed_internal_ips
    
    def do_OPTIONS(self) -> None:
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Owner-Pack")
        self.end_headers()
    
    def do_POST(self) -> None:
        if not self._check_client_allowed():
            self._send_json_response(403, {"success": False, "error": "Forbidden: Only local connections allowed", "error_type": "forbidden_client"})
            return
        
        if self.path != "/proxy/request":
            self._send_json_response(404, {"success": False, "error": f"Not found: {self.path}", "error_type": "not_found"})
            return
        
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length > 0 else b""
            request_data = json.loads(body.decode("utf-8")) if body else {}
        except json.JSONDecodeError as e:
            self._send_json_response(400, {"success": False, "error": f"Invalid JSON: {e}", "error_type": "invalid_json"})
            return
        except Exception as e:
            self._send_json_response(400, {"success": False, "error": f"Request error: {e}", "error_type": "request_error"})
            return
        
        owner_pack = self.headers.get("X-Owner-Pack") or request_data.get("owner_pack")
        if not owner_pack:
            self._send_json_response(400, {"success": False, "error": "Missing owner_pack", "error_type": "missing_owner_pack"})
            return
        
        request_data["owner_pack"] = owner_pack
        
        try:
            proxy_request = ProxyRequest.from_dict(request_data)
            response = self._process_request(proxy_request)
            status = 200 if response.success else (403 if not response.allowed else 502)
            self._send_json_response(status, response.to_dict())
        except Exception as e:
            self._send_json_response(500, {"success": False, "error": str(e), "error_type": type(e).__name__})
    
    def _process_request(self, request: ProxyRequest) -> ProxyResponse:
        """リクエストを処理"""
        try:
            parsed = urlparse(request.url)
            domain = parsed.hostname or ""
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
        except Exception as e:
            response = ProxyResponse(
                success=False,
                error=f"Invalid URL: {e}",
                error_type="invalid_url",
                allowed=False
            )
            self._log_request(
                request, "", 0, False, 0,
                error=str(e), allowed=False, rejection_reason="invalid_url"
            )
            return response
        
        # ネットワーク権限チェック
        if self.network_grant_manager:
            check_result = self.network_grant_manager.check_access(request.owner_pack, domain, port)
            if not check_result.allowed:
                response = ProxyResponse(
                    success=False,
                    allowed=False,
                    rejection_reason=check_result.reason,
                    error=f"Network access denied: {check_result.reason}",
                    error_type="network_denied"
                )
                # 拒否を監査ログに記録
                self._log_request(
                    request, domain, port, False, 0,
                    error=response.error, allowed=False, rejection_reason=check_result.reason
                )
                return response
        
        # HTTPリクエストを実行
        try:
            response = self._execute_http_request(request, domain, port)
            # 成功/失敗を監査ログに記録
            self._log_request(
                request, domain, port,
                success=response.success,
                status_code=response.status_code,
                error=response.error if not response.success else None,
                allowed=True
            )
            return response
        except Exception as e:
            error_msg = str(e)
            response = ProxyResponse(
                success=False,
                error=error_msg,
                error_type=type(e).__name__,
                allowed=True  # 許可はされたが実行失敗
            )
            # 実行失敗を監査ログに記録
            self._log_request(
                request, domain, port, False, 0,
                error=error_msg, allowed=True
            )
            return response
    
    def _execute_http_request(self, request: ProxyRequest, domain: str, port: int) -> ProxyResponse:
        """HTTPリクエストを実行"""
        try:
            import http.client
            parsed = urlparse(request.url)
            
            if parsed.scheme == "https":
                context = ssl.create_default_context()
                conn = http.client.HTTPSConnection(domain, port, timeout=request.timeout_seconds, context=context)
            else:
                conn = http.client.HTTPConnection(domain, port, timeout=request.timeout_seconds)
            
            try:
                path = parsed.path or "/"
                if parsed.query:
                    path = f"{path}?{parsed.query}"
                
                headers = dict(request.headers)
                if "Host" not in headers:
                    headers["Host"] = domain
                
                conn.request(request.method, path, body=request.body, headers=headers)
                resp = conn.getresponse()
                
                resp_headers = {}
                for key, value in resp.getheaders():
                    resp_headers[key] = value
                
                resp_body = resp.read()
                
                try:
                    body_str = resp_body.decode("utf-8")
                except UnicodeDecodeError:
                    import base64
                    body_str = base64.b64encode(resp_body).decode("ascii")
                    resp_headers["X-Proxy-Body-Encoding"] = "base64"
                
                return ProxyResponse(
                    success=True,
                    status_code=resp.status,
                    headers=resp_headers,
                    body=body_str,
                    allowed=True
                )
            finally:
                conn.close()
        except socket.timeout:
            return ProxyResponse(
                success=False,
                error="Request timed out",
                error_type="timeout",
                allowed=True  # 許可はされたがタイムアウト
            )
        except Exception as e:
            return ProxyResponse(
                success=False,
                error=str(e),
                error_type=type(e).__name__,
                allowed=True  # 許可はされたが実行失敗
            )
    
    def _log_request(
        self,
        request: ProxyRequest,
        domain: str,
        port: int,
        success: bool,
        status_code: int,
        error: str = None,
        allowed: bool = True,
        rejection_reason: str = None
    ) -> None:
        """リクエストを監査ログに記録"""
        if self.audit_logger:
            try:
                self.audit_logger.log_network_event(
                    pack_id=request.owner_pack,
                    domain=domain,
                    port=port,
                    allowed=allowed,
                    reason=rejection_reason if not allowed else None,
                    request_details={
                        "method": request.method,
                        "url": request.url,
                        "success": success,
                        "status_code": status_code,
                        "error": error,
                    }
                )
            except Exception:
                pass


class EgressProxyServer:
    """Egress Proxy サーバー"""
    
    DEFAULT_HOST = "127.0.0.1"
    DEFAULT_PORT = 8766
    
    def __init__(self, host: str = None, port: int = None, network_grant_manager=None, audit_logger=None):
        self.host = host or self.DEFAULT_HOST
        self.port = port or self.DEFAULT_PORT
        self._network_grant_manager = network_grant_manager
        self._audit_logger = audit_logger
        self._server: Optional[EgressHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
    
    def start(self) -> bool:
        with self._lock:
            if self._server is not None:
                return False
            try:
                self._server = EgressHTTPServer(
                    (self.host, self.port),
                    EgressProxyHandler,
                    network_grant_manager=self._network_grant_manager,
                    audit_logger=self._audit_logger
                )
                self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
                self._thread.start()
                print(f"[EgressProxy] Started on http://{self.host}:{self.port}")
                if self._audit_logger:
                    self._audit_logger.log_system_event(event_type="egress_proxy_start", success=True, details={"host": self.host, "port": self.port})
                return True
            except Exception as e:
                print(f"[EgressProxy] Failed to start: {e}")
                self._server = None
                self._thread = None
                return False
    
    def stop(self) -> bool:
        with self._lock:
            if self._server is None:
                return False
            try:
                self._server.shutdown()
                self._server = None
                if self._thread:
                    self._thread.join(timeout=5)
                    self._thread = None
                print("[EgressProxy] Stopped")
                if self._audit_logger:
                    self._audit_logger.log_system_event(event_type="egress_proxy_stop", success=True)
                return True
            except Exception as e:
                print(f"[EgressProxy] Error stopping: {e}")
                return False
    
    def is_running(self) -> bool:
        with self._lock:
            return self._server is not None and self._thread is not None and self._thread.is_alive()
    
    def get_endpoint(self) -> str:
        return f"http://{self.host}:{self.port}/proxy/request"
    
    def set_network_grant_manager(self, manager) -> None:
        self._network_grant_manager = manager
        if self._server:
            self._server.network_grant_manager = manager
    
    def set_audit_logger(self, logger) -> None:
        self._audit_logger = logger
        if self._server:
            self._server.audit_logger = logger


def make_proxy_request(proxy_url: str, owner_pack: str, method: str, url: str, headers: Dict[str, str] = None, body: str = None, timeout_seconds: float = 30.0) -> ProxyResponse:
    """プロキシ経由でHTTPリクエストを送信"""
    import http.client
    try:
        parsed = urlparse(proxy_url)
        conn = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=timeout_seconds + 5)
        try:
            request_body = json.dumps({
                "owner_pack": owner_pack, "method": method, "url": url,
                "headers": headers or {}, "body": body or "", "timeout_seconds": timeout_seconds,
            }).encode("utf-8")
            conn.request("POST", parsed.path or "/proxy/request", body=request_body, headers={"Content-Type": "application/json", "X-Owner-Pack": owner_pack})
            resp = conn.getresponse()
            resp_body = resp.read().decode("utf-8")
            resp_data = json.loads(resp_body)
            return ProxyResponse(
                success=resp_data.get("success", False), status_code=resp_data.get("status_code", 0),
                headers=resp_data.get("headers", {}), body=resp_data.get("body", ""),
                error=resp_data.get("error"), error_type=resp_data.get("error_type"),
                allowed=resp_data.get("allowed", True), rejection_reason=resp_data.get("rejection_reason"),
            )
        finally:
            conn.close()
    except Exception as e:
        return ProxyResponse(success=False, error=str(e), error_type=type(e).__name__)


_global_egress_proxy: Optional[EgressProxyServer] = None
_proxy_lock = threading.Lock()


def get_egress_proxy() -> EgressProxyServer:
    global _global_egress_proxy
    if _global_egress_proxy is None:
        with _proxy_lock:
            if _global_egress_proxy is None:
                _global_egress_proxy = EgressProxyServer()
    return _global_egress_proxy


def initialize_egress_proxy(host: str = None, port: int = None, network_grant_manager=None, audit_logger=None, auto_start: bool = True) -> EgressProxyServer:
    global _global_egress_proxy
    with _proxy_lock:
        if _global_egress_proxy and _global_egress_proxy.is_running():
            _global_egress_proxy.stop()
        _global_egress_proxy = EgressProxyServer(host=host, port=port, network_grant_manager=network_grant_manager, audit_logger=audit_logger)
        if auto_start:
            _global_egress_proxy.start()
    return _global_egress_proxy


def shutdown_egress_proxy() -> None:
    global _global_egress_proxy
    with _proxy_lock:
        if _global_egress_proxy:
            _global_egress_proxy.stop()
            _global_egress_proxy = None
