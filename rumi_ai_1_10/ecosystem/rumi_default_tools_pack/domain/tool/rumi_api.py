from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

_PACK_ROOT = Path(__file__).resolve().parents[2]
_DEFAULTSPACK_ROOT = _PACK_ROOT.parent / "defaultspack"
for _path in (str(_PACK_ROOT), str(_DEFAULTSPACK_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from blocks._common import ok, error
from domain.tool_policy.internal_context import internal_tool_decision_allows


SAFE_MUTATION_PREFIXES = {
    "/api/chat/",
    "/api/agent/",
    "/api/context/",
    "/api/research/",
    "/api/tools/invoke",
}

DENIED_PREFIXES = {
    "/api/integrations/secrets",
}


def run(arguments: dict[str, Any], context: dict[str, Any] | None = None):
    action = str(arguments.get("action") or "list_routes").strip()
    if action == "list_routes":
        return ok({"routes": _route_catalog(), "count": len(_route_catalog())})
    if action != "request":
        return error("unsupported action: " + action, "INVALID_ACTION")

    method = str(arguments.get("method") or "GET").upper().strip()
    path = str(arguments.get("path") or "").strip()
    if method not in {"GET", "POST", "PUT", "DELETE"}:
        return error("method must be GET, POST, PUT, or DELETE", "INVALID_METHOD")
    if not path.startswith("/api/") and not path.startswith("/v1/"):
        return error("path must start with /api/ or /v1/", "INVALID_PATH")
    if any(path.startswith(prefix) for prefix in DENIED_PREFIXES):
        return error("path is not callable through rumi_api tool: " + path, "PATH_DENIED")
    if method != "GET" and not _mutation_allowed(path, arguments, context or {}):
        return ok(
            {
                "approval_required": True,
                "tool_name": "rumi_api",
                "method": method,
                "path": path,
                "reason": "mutation requires allow_mutation and an approved/yolo tool context",
            }
        )

    try:
        payload = _request(method, path, arguments.get("body"))
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
            parsed = json.loads(body)
        except Exception:
            parsed = {"raw": body if "body" in locals() else ""}
        return error(
            "local API returned HTTP " + str(exc.code),
            "HTTP_ERROR",
            {"status_code": exc.code, "response": parsed},
        )
    except Exception as exc:
        return error("local API request failed: " + str(exc), "REQUEST_FAILED")

    return ok(payload)


def _route_catalog() -> list[dict[str, str]]:
    pack_routes = _pack_route_catalog()
    try:
        from transport.registry import _FALLBACK_HTTP_ROUTE_SPECS

        routes = [
            {"method": spec.method, "path": spec.pattern, "block_module": spec.block_module}
            for spec in _FALLBACK_HTTP_ROUTE_SPECS
        ]
        routes.extend(pack_routes)
        return routes
    except Exception:
        routes = [
            {"method": "GET", "path": "/api/health", "block_module": "transport.http"},
            {"method": "GET", "path": "/api/chat/conversations", "block_module": "blocks.chat.list_conversations"},
        ]
        routes.extend(pack_routes)
        return routes


def _pack_route_catalog() -> list[dict[str, str]]:
    routes: list[dict[str, str]] = []
    ecosystem_dir = _PACK_ROOT.parent
    if not ecosystem_dir.exists():
        return routes
    for routes_path in sorted(ecosystem_dir.glob("*/routes.json")):
        try:
            payload = json.loads(routes_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for route in payload.get("routes", []):
            if not isinstance(route, dict):
                continue
            method = str(route.get("method") or "").strip()
            path = str(route.get("path") or "").strip()
            if method and path:
                routes.append({"method": method, "path": path, "block_module": str(route.get("block_module") or "")})
    return routes


def _mutation_allowed(path: str, arguments: dict[str, Any], context: dict[str, Any]) -> bool:
    if not bool(arguments.get("allow_mutation")):
        return False
    if not any(path.startswith(prefix) for prefix in SAFE_MUTATION_PREFIXES):
        return False
    policy = context.get("profile_policy") if isinstance(context.get("profile_policy"), dict) else {}
    return (
        bool(policy.get("yolo_mode"))
        or internal_tool_decision_allows(context)
    )


def _request(method: str, path: str, body: Any) -> dict[str, Any]:
    host = os.environ.get("DEFAULTS_HTTP_HOST", "127.0.0.1")
    port = os.environ.get("DEFAULTS_HTTP_PORT", os.environ.get("RUMI_DEFAULTSPACK_PORT", "8766"))
    url = "http://{}:{}{}".format(host, port, path)
    data = None
    headers = {"Content-Type": "application/json"}
    if method in {"POST", "PUT"}:
        data = json.dumps(body if isinstance(body, dict) else {}).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=15) as response:
        raw = response.read().decode("utf-8", errors="replace")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}
