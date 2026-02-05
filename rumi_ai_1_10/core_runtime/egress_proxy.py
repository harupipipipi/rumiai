"""
egress_proxy.py - UDS Egress Proxy サーバー

Packからの外部ネットワーク通信を仲介するプロキシサーバー。
Pack別UDSソケットでpack_idを確定し（payloadは無視）、
network grant に基づいて allow/deny を判定し、監査ログに記録する。

セキュリティ防御:
- 内部IP禁止（localhost/private/link-local/CGNAT/multicast等）
- DNS rebinding対策（解決結果が内部IPなら拒否）
- リダイレクト上限（3ホップ、各ホップでgrant再チェック）
- リクエスト/レスポンスサイズ制限
- タイムアウト制限
- ヘッダー数/サイズ制限
- メソッド制限

PR-B変更:
- 内部宛て禁止をgrant判定より前に（B1）
- 巨大レスポンスは必ず失敗化（B2）
- Packへの返却は汎用理由、auditに詳細
"""

from __future__ import annotations

import base64
import http.client
import ipaddress
import json
import os
import socket
import ssl
import stat
import struct
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse, urljoin


# ============================================================
# 定数
# ============================================================

# サイズ制限
MAX_REQUEST_SIZE = 1 * 1024 * 1024   # 1MB
MAX_RESPONSE_SIZE = 4 * 1024 * 1024  # 4MB
MAX_RESPONSE_READ_CHUNK = 65536      # 64KB per chunk

# タイムアウト
DEFAULT_TIMEOUT = 30.0
MAX_TIMEOUT = 120.0

# リダイレクト
MAX_REDIRECTS = 3

# メソッド制限
ALLOWED_METHODS = {"GET", "HEAD", "POST", "PUT", "DELETE", "PATCH"}

# ヘッダー制限
MAX_HEADER_COUNT = 100
MAX_HEADER_NAME_LENGTH = 256
MAX_HEADER_VALUE_LENGTH = 8192

# セキュリティブロック用の汎用エラーメッセージ（Pack向け）
GENERIC_SECURITY_BLOCK_MESSAGE = "Request blocked by security policy"
GENERIC_SECURITY_BLOCK_TYPE = "blocked"

# 禁止IPレンジ（IPv4）
BLOCKED_IPV4_NETWORKS = [
    ipaddress.IPv4Network("0.0.0.0/8"),       # "this network"
    ipaddress.IPv4Network("10.0.0.0/8"),      # private
    ipaddress.IPv4Network("100.64.0.0/10"),   # CGNAT
    ipaddress.IPv4Network("127.0.0.0/8"),     # loopback
    ipaddress.IPv4Network("169.254.0.0/16"),  # link-local
    ipaddress.IPv4Network("172.16.0.0/12"),   # private
    ipaddress.IPv4Network("192.168.0.0/16"),  # private
    ipaddress.IPv4Network("224.0.0.0/4"),     # multicast
    ipaddress.IPv4Network("240.0.0.0/4"),     # reserved
]

# 禁止IPレンジ（IPv6）
BLOCKED_IPV6_NETWORKS = [
    ipaddress.IPv6Network("::/128"),          # unspecified
    ipaddress.IPv6Network("::1/128"),         # loopback
    ipaddress.IPv6Network("fc00::/7"),        # ULA
    ipaddress.IPv6Network("fe80::/10"),       # link-local
    ipaddress.IPv6Network("ff00::/8"),        # multicast
]

# ブロードキャストアドレス
BLOCKED_IPV4_ADDRESSES = {
    ipaddress.IPv4Address("255.255.255.255"),
}


# ============================================================
# IP検証ユーティリティ
# ============================================================

def is_internal_ip(ip_str: str) -> Tuple[bool, str]:
    """
    IPが内部/禁止レンジか判定
    
    Returns:
        (is_blocked, reason)
    """
    try:
        ip = ipaddress.ip_address(ip_str)
        
        if isinstance(ip, ipaddress.IPv4Address):
            # ブロードキャストチェック
            if ip in BLOCKED_IPV4_ADDRESSES:
                return True, f"IP {ip} is a broadcast address"
            
            # ネットワークレンジチェック
            for net in BLOCKED_IPV4_NETWORKS:
                if ip in net:
                    return True, f"IP {ip} is in blocked range {net}"
        else:
            # IPv6
            for net in BLOCKED_IPV6_NETWORKS:
                if ip in net:
                    return True, f"IP {ip} is in blocked range {net}"
        
        return False, ""
    except ValueError as e:
        return True, f"Invalid IP address: {e}"


def _is_ip_literal(host: str) -> bool:
    """ホストがIPリテラルかどうか判定"""
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def resolve_and_check_ip(hostname: str) -> Tuple[bool, str, List[str]]:
    """
    ホスト名をDNS解決し、内部IPが含まれていないかチェック
    
    Returns:
        (is_blocked, reason, resolved_ips)
    """
    # IPリテラルの場合は直接チェック
    if _is_ip_literal(hostname):
        is_blocked, reason = is_internal_ip(hostname)
        return is_blocked, reason, [hostname] if not is_blocked else []
    
    try:
        # getaddrinfo で A/AAAA 両方を取得
        results = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        resolved_ips = list(set(r[4][0] for r in results))
        
        if not resolved_ips:
            return True, f"DNS resolution failed: no addresses for {hostname}", []
        
        # 全IPをチェック（1つでも内部なら拒否）
        for ip in resolved_ips:
            is_internal, reason = is_internal_ip(ip)
            if is_internal:
                return True, f"DNS rebinding blocked: {reason}", resolved_ips
        
        return False, "", resolved_ips
    except socket.gaierror as e:
        return True, f"DNS resolution failed: {e}", []
    except Exception as e:
        return True, f"DNS check error: {e}", []


# ============================================================
# length-prefix JSON プロトコル
# ============================================================

def read_length_prefixed_json(sock: socket.socket, max_size: int) -> Optional[Dict[str, Any]]:
    """
    length-prefix JSON を読み取る（4バイトビッグエンディアン + JSON）
    """
    # 4バイトの長さプレフィックスを読む
    length_data = b""
    while len(length_data) < 4:
        chunk = sock.recv(4 - len(length_data))
        if not chunk:
            return None
        length_data += chunk
    
    length = struct.unpack(">I", length_data)[0]
    
    if length > max_size:
        raise ValueError(f"Message too large: {length} > {max_size}")
    
    if length == 0:
        return {}
    
    # JSONペイロードを読む
    data = b""
    while len(data) < length:
        chunk = sock.recv(min(length - len(data), 65536))
        if not chunk:
            raise ValueError("Connection closed while reading payload")
        data += chunk
    
    return json.loads(data.decode("utf-8"))


def write_length_prefixed_json(sock: socket.socket, data: Dict[str, Any]) -> None:
    """length-prefix JSON を書き込む"""
    payload = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
    length = struct.pack(">I", len(payload))
    sock.sendall(length + payload)


# ============================================================
# リクエストバリデーション
# ============================================================

def validate_request(request: Dict[str, Any]) -> Tuple[bool, str]:
    """リクエストのバリデーション"""
    # メソッドチェック
    method = request.get("method", "").upper()
    if not method:
        return False, "Method is required"
    if method not in ALLOWED_METHODS:
        return False, f"Method not allowed: {method}. Allowed: {ALLOWED_METHODS}"
    
    # URLチェック
    url = request.get("url", "")
    if not url:
        return False, "URL is required"
    
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False, f"Unsupported scheme: {parsed.scheme}"
        if not parsed.hostname:
            return False, "URL must have a hostname"
    except Exception as e:
        return False, f"Invalid URL: {e}"
    
    # ヘッダーチェック
    headers = request.get("headers", {})
    if not isinstance(headers, dict):
        return False, "Headers must be a dict"
    if len(headers) > MAX_HEADER_COUNT:
        return False, f"Too many headers: {len(headers)} > {MAX_HEADER_COUNT}"
    
    for name, value in headers.items():
        if len(str(name)) > MAX_HEADER_NAME_LENGTH:
            return False, f"Header name too long: {len(str(name))} > {MAX_HEADER_NAME_LENGTH}"
        if len(str(value)) > MAX_HEADER_VALUE_LENGTH:
            return False, f"Header value too long: {len(str(value))} > {MAX_HEADER_VALUE_LENGTH}"
    
    # タイムアウトチェック
    timeout = request.get("timeout_seconds", DEFAULT_TIMEOUT)
    try:
        timeout = float(timeout)
    except (TypeError, ValueError):
        return False, f"Invalid timeout: {timeout}"
    if timeout <= 0:
        return False, f"Timeout must be positive: {timeout}"
    if timeout > MAX_TIMEOUT:
        return False, f"Timeout too large: {timeout} > {MAX_TIMEOUT}"
    
    return True, ""


# ============================================================
# 監査ログヘルパー
# ============================================================

def _log_network_event(
    audit_logger,
    pack_id: str,
    domain: str,
    port: int,
    allowed: bool,
    reason: str = None,
    method: str = None,
    url: str = None,
    final_url: str = None,
    latency_ms: float = 0,
    status_code: int = None,
    error_type: str = None,
    redirect_hops: int = 0,
    bytes_read: int = 0,
    blocked_reason: str = None,
    max_response_bytes: int = None,
    check_type: str = None
) -> None:
    """監査ログにネットワークイベントを記録"""
    if audit_logger is None:
        return
    
    try:
        request_details = {
            "method": method,
            "url": url,
            "final_url": final_url,
            "latency_ms": latency_ms,
            "redirect_hops": redirect_hops,
            "bytes_read": bytes_read,
        }
        
        if status_code is not None:
            request_details["status_code"] = status_code
        if error_type is not None:
            request_details["error_type"] = error_type
        if blocked_reason is not None:
            request_details["blocked_reason"] = blocked_reason
        if max_response_bytes is not None:
            request_details["max_response_bytes"] = max_response_bytes
        if check_type is not None:
            request_details["check_type"] = check_type
        
        audit_logger.log_network_event(
            pack_id=pack_id,
            domain=domain,
            port=port,
            allowed=allowed,
            reason=reason,
            request_details=request_details
        )
    except Exception as e:
        print(f"[EgressProxy] Failed to log network event: {e}")


# ============================================================
# レスポンス読み取りヘルパー（B2対応）
# ============================================================

def read_response_with_limit(resp, max_size: int) -> Tuple[bytes, bool, int]:
    """
    レスポンスボディを上限付きで読み取る
    
    Returns:
        (data, exceeded, bytes_read)
        - data: 読み取ったデータ（超過時は途中まで）
        - exceeded: 上限を超過したか
        - bytes_read: 実際に読み取ったバイト数
    """
    # Content-Lengthがあれば事前チェック
    content_length = resp.getheader("Content-Length")
    if content_length:
        try:
            cl = int(content_length)
            if cl > max_size:
                # Content-Length超過：読み取らずに即失敗
                return b"", True, 0
        except (ValueError, TypeError):
            pass
    
    # チャンク読み取りで上限監視
    data = b""
    bytes_read = 0
    exceeded = False
    
    while True:
        remaining = max_size - bytes_read + 1  # +1で超過検知
        chunk_size = min(MAX_RESPONSE_READ_CHUNK, remaining)
        
        try:
            chunk = resp.read(chunk_size)
        except Exception:
            break
        
        if not chunk:
            break
        
        bytes_read += len(chunk)
        
        if bytes_read > max_size:
            # 超過検知
            exceeded = True
            data += chunk[:max_size - (bytes_read - len(chunk))]  # 上限までのデータ
            break
        
        data += chunk
    
    return data, exceeded, bytes_read


# ============================================================
# HTTPリクエスト実行
# ============================================================

def execute_http_request(
    pack_id: str,
    request: Dict[str, Any],
    network_grant_manager,
    audit_logger
) -> Dict[str, Any]:
    """
    HTTPリクエストを実行（リダイレクト、セキュリティチェック込み）
    
    pack_id はUDSソケットから確定済み（payloadのowner_packは無視）
    
    PR-B変更:
    - B1: 内部宛て禁止をgrant判定より前に
    - B2: 巨大レスポンスは必ず失敗化
    - Packへの返却は汎用理由、auditに詳細
    """
    start_time = time.time()
    
    method = request.get("method", "GET").upper()
    original_url = request.get("url", "")
    headers = request.get("headers", {})
    body = request.get("body")
    timeout = min(float(request.get("timeout_seconds", DEFAULT_TIMEOUT)), MAX_TIMEOUT)
    
    current_url = original_url
    redirect_hops = 0
    bytes_read = 0
    final_url = original_url
    last_domain = ""
    last_port = 0
    
    result = {
        "success": False,
        "status_code": 0,
        "headers": {},
        "body": "",
        "error": None,
        "error_type": None,
        "latency_ms": 0,
        "redirect_hops": 0,
        "bytes_read": 0,
        "final_url": original_url,
    }
    
    try:
        while redirect_hops <= MAX_REDIRECTS:
            parsed = urlparse(current_url)
            domain = parsed.hostname or ""
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            last_domain = domain
            last_port = port
            
            # ============================================================
            # B1: 内部宛て禁止を最優先判定（grantより前）
            # ============================================================
            
            # 1. IPリテラルチェック（内部IP禁止）
            if _is_ip_literal(domain):
                is_blocked, reason = is_internal_ip(domain)
                if is_blocked:
                    # Pack向けは汎用メッセージ
                    result["error"] = GENERIC_SECURITY_BLOCK_MESSAGE
                    result["error_type"] = GENERIC_SECURITY_BLOCK_TYPE
                    result["latency_ms"] = (time.time() - start_time) * 1000
                    result["redirect_hops"] = redirect_hops
                    result["final_url"] = current_url
                    
                    # auditには詳細を記録
                    _log_network_event(
                        audit_logger, pack_id, domain, port, False,
                        reason=reason,
                        method=method, url=original_url, final_url=current_url,
                        latency_ms=result["latency_ms"],
                        redirect_hops=redirect_hops,
                        blocked_reason="internal_ip_blocked",
                        check_type="proxy_request"
                    )
                    return result
            
            # 2. DNS解決 & 内部IP検証（DNS rebinding対策）
            is_blocked, dns_reason, resolved_ips = resolve_and_check_ip(domain)
            if is_blocked:
                # Pack向けは汎用メッセージ
                result["error"] = GENERIC_SECURITY_BLOCK_MESSAGE
                result["error_type"] = GENERIC_SECURITY_BLOCK_TYPE
                result["latency_ms"] = (time.time() - start_time) * 1000
                result["redirect_hops"] = redirect_hops
                result["final_url"] = current_url
                
                # blocked_reasonを判定（dns_rebindingかdns_blockedか）
                blocked_reason = "dns_blocked"
                if "rebinding" in dns_reason.lower():
                    blocked_reason = "dns_rebinding_blocked"
                
                # auditには詳細を記録
                _log_network_event(
                    audit_logger, pack_id, domain, port, False,
                    reason=dns_reason,
                    method=method, url=original_url, final_url=current_url,
                    latency_ms=result["latency_ms"],
                    redirect_hops=redirect_hops,
                    blocked_reason=blocked_reason,
                    check_type="proxy_request"
                )
                return result
            
            # ============================================================
            # 3. Grant チェック（内部宛て判定の後）
            # ============================================================
            if network_grant_manager:
                grant_result = network_grant_manager.check_access(pack_id, domain, port)
                if not grant_result.allowed:
                    result["error"] = f"Network access denied: {grant_result.reason}"
                    result["error_type"] = "grant_denied"
                    result["latency_ms"] = (time.time() - start_time) * 1000
                    result["redirect_hops"] = redirect_hops
                    result["final_url"] = current_url
                    
                    _log_network_event(
                        audit_logger, pack_id, domain, port, False,
                        reason=grant_result.reason,
                        method=method, url=original_url, final_url=current_url,
                        latency_ms=result["latency_ms"],
                        redirect_hops=redirect_hops,
                        blocked_reason="grant_denied",
                        check_type="proxy_request"
                    )
                    return result
            
            # ============================================================
            # 4. HTTP接続 & リクエスト実行
            # ============================================================
            conn = None
            try:
                if parsed.scheme == "https":
                    context = ssl.create_default_context()
                    conn = http.client.HTTPSConnection(domain, port, timeout=timeout, context=context)
                else:
                    conn = http.client.HTTPConnection(domain, port, timeout=timeout)
                
                path = parsed.path or "/"
                if parsed.query:
                    path = f"{path}?{parsed.query}"
                
                req_headers = dict(headers)
                if "Host" not in req_headers and "host" not in req_headers:
                    req_headers["Host"] = domain
                
                req_body = None
                if body is not None:
                    req_body = body.encode("utf-8") if isinstance(body, str) else body
                
                conn.request(method, path, body=req_body, headers=req_headers)
                resp = conn.getresponse()
                
                resp_headers = {k: v for k, v in resp.getheaders()}
                
                # ============================================================
                # B2: 巨大レスポンスは必ず失敗化
                # ============================================================
                resp_body, size_exceeded, read_bytes = read_response_with_limit(resp, MAX_RESPONSE_SIZE)
                bytes_read += read_bytes
                
                if size_exceeded:
                    result["error"] = f"Response too large (max: {MAX_RESPONSE_SIZE} bytes)"
                    result["error_type"] = "response_too_large"
                    result["latency_ms"] = (time.time() - start_time) * 1000
                    result["redirect_hops"] = redirect_hops
                    result["bytes_read"] = bytes_read
                    result["final_url"] = current_url
                    
                    _log_network_event(
                        audit_logger, pack_id, domain, port, False,
                        reason=f"Response exceeded size limit: {read_bytes} bytes read, max {MAX_RESPONSE_SIZE}",
                        method=method, url=original_url, final_url=current_url,
                        latency_ms=result["latency_ms"],
                        status_code=resp.status,
                        redirect_hops=redirect_hops,
                        bytes_read=bytes_read,
                        error_type="response_too_large",
                        max_response_bytes=MAX_RESPONSE_SIZE,
                        check_type="proxy_request"
                    )
                    return result
                
                # 5. リダイレクト判定（GET/HEADのみfollow）
                if resp.status in (301, 302, 303, 307, 308) and method in ("GET", "HEAD"):
                    location = resp_headers.get("Location") or resp_headers.get("location")
                    if location:
                        redirect_hops += 1
                        if redirect_hops > MAX_REDIRECTS:
                            result["error"] = f"Too many redirects: {redirect_hops} > {MAX_REDIRECTS}"
                            result["error_type"] = "too_many_redirects"
                            result["latency_ms"] = (time.time() - start_time) * 1000
                            result["redirect_hops"] = redirect_hops
                            result["bytes_read"] = bytes_read
                            result["final_url"] = current_url
                            
                            _log_network_event(
                                audit_logger, pack_id, domain, port, False,
                                reason=result["error"],
                                method=method, url=original_url, final_url=current_url,
                                latency_ms=result["latency_ms"],
                                error_type="too_many_redirects",
                                redirect_hops=redirect_hops,
                                bytes_read=bytes_read,
                                check_type="proxy_request"
                            )
                            return result
                        
                        current_url = urljoin(current_url, location)
                        final_url = current_url
                        continue
                
                # 6. 成功
                try:
                    body_str = resp_body.decode("utf-8")
                except UnicodeDecodeError:
                    body_str = base64.b64encode(resp_body).decode("ascii")
                    resp_headers["X-Proxy-Body-Encoding"] = "base64"
                
                result["success"] = True
                result["status_code"] = resp.status
                result["headers"] = resp_headers
                result["body"] = body_str
                result["final_url"] = final_url
                result["redirect_hops"] = redirect_hops
                result["bytes_read"] = bytes_read
                result["latency_ms"] = (time.time() - start_time) * 1000
                
                _log_network_event(
                    audit_logger, pack_id, domain, port, True,
                    method=method, url=original_url, final_url=final_url,
                    latency_ms=result["latency_ms"],
                    status_code=resp.status,
                    redirect_hops=redirect_hops,
                    bytes_read=bytes_read,
                    check_type="proxy_request"
                )
                
                return result
                
            except socket.timeout:
                result["error"] = f"Request timed out after {timeout}s"
                result["error_type"] = "timeout"
                break
            except ssl.SSLError as e:
                result["error"] = f"SSL error: {e}"
                result["error_type"] = "ssl_error"
                break
            except ConnectionRefusedError:
                result["error"] = f"Connection refused to {domain}:{port}"
                result["error_type"] = "connection_refused"
                break
            except Exception as e:
                result["error"] = str(e)
                result["error_type"] = type(e).__name__
                break
            finally:
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass
    
    except Exception as e:
        result["error"] = str(e)
        result["error_type"] = type(e).__name__
    
    # エラー終了時の共通処理
    result["latency_ms"] = (time.time() - start_time) * 1000
    result["redirect_hops"] = redirect_hops
    result["bytes_read"] = bytes_read
    result["final_url"] = final_url
    
    _log_network_event(
        audit_logger, pack_id, last_domain, last_port, False,
        reason=result.get("error"),
        method=method, url=original_url, final_url=final_url,
        latency_ms=result["latency_ms"],
        error_type=result.get("error_type"),
        redirect_hops=redirect_hops,
        bytes_read=bytes_read,
        check_type="proxy_request"
    )
    
    return result


# ============================================================
# UDSソケット管理
# ============================================================

class UDSSocketManager:
    """Pack別UDSソケット管理"""
    
    DEFAULT_BASE_DIR = "/run/rumi/egress/packs"
    FALLBACK_BASE_DIR = "/tmp/rumi/egress/packs"
    
    def __init__(self):
        self._base_dir: Optional[Path] = None
        self._active_sockets: Dict[str, Path] = {}
        self._lock = threading.Lock()
    
    def _get_base_dir(self) -> Path:
        """ベースディレクトリを取得（環境変数 > デフォルト > フォールバック）"""
        if self._base_dir is not None:
            return self._base_dir
        
        # 環境変数
        env_dir = os.environ.get("RUMI_EGRESS_SOCK_DIR")
        if env_dir:
            path = Path(env_dir)
            try:
                path.mkdir(parents=True, exist_ok=True)
                self._base_dir = path
                return path
            except Exception:
                pass
        
        # デフォルト試行
        default = Path(self.DEFAULT_BASE_DIR)
        try:
            default.mkdir(parents=True, exist_ok=True)
            self._base_dir = default
            return default
        except Exception:
            pass
        
        # フォールバック
        fallback = Path(self.FALLBACK_BASE_DIR)
        try:
            fallback.mkdir(parents=True, exist_ok=True)
            self._base_dir = fallback
            return fallback
        except Exception as e:
            raise RuntimeError(f"Failed to create socket directory: {e}")
    
    def get_socket_path(self, pack_id: str) -> Path:
        """Pack IDからソケットパスを取得"""
        # pack_id をサニタイズ
        safe_id = pack_id.replace("/", "_").replace(":", "_").replace("..", "_").replace("\\", "_")
        return self._get_base_dir() / f"{safe_id}.sock"
    
    def ensure_socket(self, pack_id: str) -> Tuple[bool, str, Optional[Path]]:
        """ソケットファイルを確保（docker run前に必須）"""
        with self._lock:
            try:
                sock_path = self.get_socket_path(pack_id)
                
                # 既存ソケットを削除
                if sock_path.exists():
                    try:
                        sock_path.unlink()
                    except Exception as e:
                        return False, f"Failed to remove existing socket: {e}", None
                
                # 親ディレクトリ確保
                try:
                    sock_path.parent.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    return False, f"Failed to create socket directory: {e}", None
                
                self._active_sockets[pack_id] = sock_path
                return True, "", sock_path
            except Exception as e:
                return False, f"Failed to ensure socket: {e}", None
    
    def cleanup_socket(self, pack_id: str) -> None:
        """ソケットをクリーンアップ"""
        with self._lock:
            if pack_id in self._active_sockets:
                sock_path = self._active_sockets.pop(pack_id)
                try:
                    if sock_path.exists():
                        sock_path.unlink()
                except Exception:
                    pass
    
    def get_base_dir_path(self) -> Path:
        """ベースディレクトリパスを取得"""
        return self._get_base_dir()


# ============================================================
# UDSサーバー（Pack別）
# ============================================================

class UDSEgressServer:
    """Pack別UDSソケットでリッスンするEgressサーバー"""
    
    def __init__(self, pack_id: str, socket_path: Path, network_grant_manager, audit_logger):
        self.pack_id = pack_id
        self.socket_path = socket_path
        self._network_grant_manager = network_grant_manager
        self._audit_logger = audit_logger
        self._server_socket: Optional[socket.socket] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
    
    def start(self) -> bool:
        """サーバーを起動"""
        with self._lock:
            if self._running:
                return True
            
            try:
                # 既存ソケットファイルを削除
                if self.socket_path.exists():
                    self.socket_path.unlink()
                
                # UDSソケット作成
                self._server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self._server_socket.bind(str(self.socket_path))
                self._server_socket.listen(5)
                self._server_socket.settimeout(1.0)  # accept用タイムアウト
                
                # パーミッション設定（コンテナ内の nobody からアクセス可能にする）
                try:
                    os.chmod(self.socket_path, 0o666)
                except Exception:
                    pass  # Windowsでは失敗する可能性
                
                self._running = True
                self._thread = threading.Thread(target=self._serve_forever, daemon=True)
                self._thread.start()
                
                print(f"[UDSEgressServer] Started for pack '{self.pack_id}' at {self.socket_path}")
                return True
            except Exception as e:
                print(f"[UDSEgressServer] Failed to start for {self.pack_id}: {e}")
                self._cleanup()
                return False
    
    def stop(self) -> None:
        """サーバーを停止"""
        with self._lock:
            self._running = False
            if self._server_socket:
                try:
                    self._server_socket.close()
                except Exception:
                    pass
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=5)
            self._cleanup()
            print(f"[UDSEgressServer] Stopped for pack '{self.pack_id}'")
    
    def _cleanup(self) -> None:
        """クリーンアップ"""
        try:
            if self.socket_path and self.socket_path.exists():
                self.socket_path.unlink()
        except Exception:
            pass
        self._server_socket = None
        self._thread = None
    
    def _serve_forever(self) -> None:
        """リクエストを処理し続ける"""
        while self._running:
            try:
                client_sock, _ = self._server_socket.accept()
                # 接続ごとにスレッド生成
                threading.Thread(
                    target=self._handle_client,
                    args=(client_sock,),
                    daemon=True
                ).start()
            except socket.timeout:
                continue
            except OSError:
                # ソケットがクローズされた
                if self._running:
                    break
            except Exception as e:
                if self._running:
                    print(f"[UDSEgressServer] Accept error for {self.pack_id}: {e}")
    
    def _handle_client(self, client_sock: socket.socket) -> None:
        """クライアント接続を処理"""
        try:
            client_sock.settimeout(DEFAULT_TIMEOUT)
            
            # リクエスト読み取り
            request = read_length_prefixed_json(client_sock, MAX_REQUEST_SIZE)
            if request is None:
                return
            
            # バリデーション
            valid, reason = validate_request(request)
            if not valid:
                response = {
                    "success": False,
                    "error": reason,
                    "error_type": "validation_error"
                }
                write_length_prefixed_json(client_sock, response)
                return
            
            # pack_id はソケットパスから確定済み（payloadのowner_packは無視）
            response = execute_http_request(
                pack_id=self.pack_id,
                request=request,
                network_grant_manager=self._network_grant_manager,
                audit_logger=self._audit_logger
            )
            
            write_length_prefixed_json(client_sock, response)
            
        except ValueError as e:
            # サイズ超過などのプロトコルエラー
            try:
                response = {
                    "success": False,
                    "error": str(e),
                    "error_type": "protocol_error"
                }
                write_length_prefixed_json(client_sock, response)
            except Exception:
                pass
        except Exception as e:
            try:
                response = {
                    "success": False,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
                write_length_prefixed_json(client_sock, response)
            except Exception:
                pass
        finally:
            try:
                client_sock.close()
            except Exception:
                pass


# ============================================================
# UDS Egress Proxy Manager
# ============================================================

class UDSEgressProxyManager:
    """Pack別UDSサーバーを管理するマネージャ"""
    
    def __init__(self, network_grant_manager=None, audit_logger=None):
        self._socket_manager = UDSSocketManager()
        self._servers: Dict[str, UDSEgressServer] = {}
        self._network_grant_manager = network_grant_manager
        self._audit_logger = audit_logger
        self._lock = threading.Lock()
    
    def set_network_grant_manager(self, manager) -> None:
        """NetworkGrantManagerを設定"""
        self._network_grant_manager = manager
        with self._lock:
            for server in self._servers.values():
                server._network_grant_manager = manager
    
    def set_audit_logger(self, logger) -> None:
        """AuditLoggerを設定"""
        self._audit_logger = logger
        with self._lock:
            for server in self._servers.values():
                server._audit_logger = logger
    
    def ensure_pack_socket(self, pack_id: str) -> Tuple[bool, str, Optional[Path]]:
        """Pack用のソケットを確保しサーバーを起動"""
        with self._lock:
            # 既に起動済みならそのまま返す
            if pack_id in self._servers:
                server = self._servers[pack_id]
                return True, "", server.socket_path
            
            # ソケットパス確保
            success, error, sock_path = self._socket_manager.ensure_socket(pack_id)
            if not success:
                return False, error, None
            
            # サーバー起動
            server = UDSEgressServer(
                pack_id=pack_id,
                socket_path=sock_path,
                network_grant_manager=self._network_grant_manager,
                audit_logger=self._audit_logger
            )
            
            if not server.start():
                self._socket_manager.cleanup_socket(pack_id)
                return False, f"Failed to start UDS server for {pack_id}", None
            
            self._servers[pack_id] = server
            return True, "", sock_path
    
    def get_socket_path(self, pack_id: str) -> Optional[Path]:
        """Pack用ソケットパスを取得（存在する場合）"""
        with self._lock:
            if pack_id in self._servers:
                return self._servers[pack_id].socket_path
            return None
    
    def stop_pack_server(self, pack_id: str) -> None:
        """Pack用サーバーを停止"""
        with self._lock:
            if pack_id in self._servers:
                self._servers[pack_id].stop()
                del self._servers[pack_id]
            self._socket_manager.cleanup_socket(pack_id)
    
    def stop_all(self) -> None:
        """全サーバーを停止"""
        with self._lock:
            for pack_id in list(self._servers.keys()):
                self._servers[pack_id].stop()
                self._socket_manager.cleanup_socket(pack_id)
            self._servers.clear()
        print("[UDSEgressProxyManager] All servers stopped")
    
    def is_running(self, pack_id: str) -> bool:
        """Pack用サーバーが起動中か"""
        with self._lock:
            return pack_id in self._servers
    
    def list_active_packs(self) -> List[str]:
        """アクティブなPack一覧"""
        with self._lock:
            return list(self._servers.keys())
    
    def get_base_dir(self) -> Path:
        """ソケットのベースディレクトリを取得"""
        return self._socket_manager.get_base_dir_path()


# ============================================================
# グローバルインスタンス
# ============================================================

_global_uds_proxy_manager: Optional[UDSEgressProxyManager] = None
_uds_proxy_lock = threading.Lock()


def get_uds_egress_proxy_manager() -> UDSEgressProxyManager:
    """グローバルなUDSEgressProxyManagerを取得"""
    global _global_uds_proxy_manager
    if _global_uds_proxy_manager is None:
        with _uds_proxy_lock:
            if _global_uds_proxy_manager is None:
                _global_uds_proxy_manager = UDSEgressProxyManager()
    return _global_uds_proxy_manager


def initialize_uds_egress_proxy(
    network_grant_manager=None,
    audit_logger=None
) -> UDSEgressProxyManager:
    """UDSEgressProxyManagerを初期化"""
    global _global_uds_proxy_manager
    with _uds_proxy_lock:
        if _global_uds_proxy_manager:
            _global_uds_proxy_manager.stop_all()
        _global_uds_proxy_manager = UDSEgressProxyManager(
            network_grant_manager=network_grant_manager,
            audit_logger=audit_logger
        )
    return _global_uds_proxy_manager


def shutdown_uds_egress_proxy() -> None:
    """UDSEgressProxyManagerをシャットダウン"""
    global _global_uds_proxy_manager
    with _uds_proxy_lock:
        if _global_uds_proxy_manager:
            _global_uds_proxy_manager.stop_all()
            _global_uds_proxy_manager = None


# ============================================================
# 以下、既存のTCP版プロキシ（後方互換性のため維持）
# ============================================================


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
