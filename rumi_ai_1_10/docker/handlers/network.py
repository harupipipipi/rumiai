"""
network ハンドラ

ネットワーク通信の制御（ドメイン/ポート単位でアクセス制御）
"""

import urllib.parse
import urllib.request
import urllib.error
import socket
from typing import Any, Dict

META = {
    "requires_scope": True,
    "supports_modes": ["sandbox"],
    "description": "ネットワーク通信（許可ドメイン/ポートのみ）",
    "version": "1.0"
}


def execute(context: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    """ネットワークリクエストを実行"""
    action = args.get("action", "request")
    
    if action == "check":
        return _check_permission(context, args)
    elif action == "request":
        return _make_request(context, args)
    else:
        return {"success": False, "error": f"Unknown action: {action}"}


def _check_permission(context: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    """URLへのアクセスが許可されているかチェック"""
    url = args.get("url")
    if not url:
        return {"success": False, "error": "URL is required"}
    
    allowed, reason = _is_url_allowed(url, context)
    return {"success": True, "allowed": allowed, "reason": reason, "url": url}


def _make_request(context: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    """HTTPリクエストを実行"""
    url = args.get("url")
    if not url:
        return {"success": False, "error": "URL is required"}
    
    method = args.get("method", "GET").upper()
    headers = args.get("headers", {})
    body = args.get("body")
    timeout = args.get("timeout", 30)
    
    allowed, reason = _is_url_allowed(url, context)
    if not allowed:
        return {"success": False, "error": reason}
    
    try:
        import json as json_module
        
        data = None
        if body is not None:
            if isinstance(body, dict):
                data = json_module.dumps(body).encode("utf-8")
                if "Content-Type" not in headers:
                    headers["Content-Type"] = "application/json"
            elif isinstance(body, str):
                data = body.encode("utf-8")
        
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        
        with urllib.request.urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8", errors="replace")
            return {
                "success": True,
                "status_code": response.status,
                "headers": dict(response.headers),
                "body": response_body
            }
    
    except urllib.error.HTTPError as e:
        return {"success": False, "error": f"HTTP Error: {e.code}", "status_code": e.code}
    except urllib.error.URLError as e:
        return {"success": False, "error": f"URL Error: {e.reason}"}
    except Exception as e:
        return {"success": False, "error": f"Request failed: {e}"}


def _is_url_allowed(url: str, context: Dict[str, Any]) -> tuple:
    """URLが許可されているかチェック"""
    try:
        parsed = urllib.parse.urlparse(url)
        hostname = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        
        if not hostname:
            return False, "Invalid URL: no hostname"
        
        allowed_domains = context.get("allowed_domains", [])
        blocked_domains = context.get("blocked_domains", [])
        allowed_ports = context.get("allowed_ports", [80, 443])
        
        # ブロックリストチェック
        for blocked in blocked_domains:
            if _domain_matches(hostname, blocked):
                return False, f"Domain blocked: {hostname}"
        
        # 許可リストチェック
        if "*" not in allowed_domains:
            allowed = False
            for domain in allowed_domains:
                if _domain_matches(hostname, domain):
                    allowed = True
                    break
            if not allowed:
                return False, f"Domain not allowed: {hostname}"
        
        # ポートチェック
        if "*" not in allowed_ports and port not in allowed_ports:
            return False, f"Port not allowed: {port}"
        
        return True, "Allowed"
    
    except Exception as e:
        return False, f"URL parse error: {e}"


def _domain_matches(hostname: str, pattern: str) -> bool:
    """ドメインがパターンにマッチするか"""
    hostname = hostname.lower()
    pattern = pattern.lower()
    
    if pattern.startswith("*."):
        suffix = pattern[2:]
        return hostname.endswith("." + suffix)
    else:
        return hostname == pattern or hostname.endswith("." + pattern)
