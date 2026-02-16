"""Pack 独自ルート管理ハンドラ Mixin"""
from __future__ import annotations

import logging
import re
from typing import Optional
from urllib.parse import unquote

from ._helpers import _log_internal_error, _SAFE_ERROR_MSG

logger = logging.getLogger(__name__)

_ROUTE_PATH_RE = re.compile(r'^/api/[a-zA-Z0-9_/.\-:]+$')


class RouteHandlersMixin:
    """Pack独自ルーティングの管理・マッチング・実行ハンドラ"""

    _pack_routes: dict = {}

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
            if not isinstance(routes, list):
                continue
            for route in routes:
                if not isinstance(route, dict):
                    continue
                method = route.get("method", "GET").upper()
                path = route.get("path", "")
                if not path or not _ROUTE_PATH_RE.match(path):
                    logger.warning(f"Skipping invalid route path: {path} (pack: {pack_id})")
                    continue
                key = (method, path)
                cls._pack_routes[key] = {
                    "pack_id": pack_id,
                    "route": route,
                }
                count += 1
        logger.info(f"Loaded {count} pack custom routes")
        return count

    @classmethod
    def _match_pack_route(cls, path: str, method: str) -> Optional[dict]:
        """パスとメソッドに一致するPack独自ルートを検索"""
        key = (method.upper(), path)
        match = cls._pack_routes.get(key)
        if match:
            return match

        for (route_method, route_path), route_info in cls._pack_routes.items():
            if route_method != method.upper():
                continue
            if "{" not in route_path:
                continue
            pattern = re.sub(r'\{[^}]+\}', r'([^/]+)', route_path)
            pattern = f'^{pattern}$'
            m = re.match(pattern, path)
            if m:
                result = dict(route_info)
                result["path_params"] = m.groups()
                return result
        return None

    def _handle_pack_route_request(self, path: str, body: dict,
                                   method: str, match: dict) -> None:
        """Pack独自ルートへのリクエストを処理"""
        from ..pack_api_server import APIResponse

        pack_id = match.get("pack_id", "")
        route = match.get("route", {})
        handler_type = route.get("handler", "flow")

        try:
            if handler_type == "flow":
                flow_id = route.get("flow_id", "")
                if not flow_id:
                    self._send_response(
                        APIResponse(False, error="Route has no flow_id configured"), 500
                    )
                    return
                inputs = dict(body)
                path_params = match.get("path_params", ())
                param_names = re.findall(r'\{([^}]+)\}', route.get("path", ""))
                for name, value in zip(param_names, path_params):
                    inputs[name] = unquote(value)
                inputs["_route_method"] = method
                inputs["_route_path"] = path

                timeout = route.get("timeout", 300)
                result = self._run_flow(flow_id, inputs, timeout)
                if result.get("success"):
                    self._send_response(APIResponse(True, result))
                else:
                    status_code = result.get("status_code", 500)
                    self._send_response(
                        APIResponse(False, error=result.get("error")), status_code
                    )
            elif handler_type == "proxy":
                self._send_response(
                    APIResponse(False, error="Proxy routes not yet implemented"), 501
                )
            else:
                self._send_response(
                    APIResponse(False, error=f"Unknown handler type: {handler_type}"), 500
                )
        except Exception as e:
            _log_internal_error("handle_pack_route_request", e)
            from ..pack_api_server import APIResponse as _AR
            self._send_response(_AR(False, error=_SAFE_ERROR_MSG), 500)

    @classmethod
    def _get_registered_routes(cls) -> dict:
        """GET /api/routes — 登録済みPack独自ルート一覧"""
        routes = []
        for (method, path), info in cls._pack_routes.items():
            routes.append({
                "method": method,
                "path": path,
                "pack_id": info.get("pack_id", ""),
                "handler": info.get("route", {}).get("handler", "flow"),
            })
        return {"routes": routes, "count": len(routes)}

    @classmethod
    def _reload_pack_routes(cls) -> dict:
        """POST /api/routes/reload — ルートを再読み込み"""
        try:
            from ..di_container import get_container
            container = get_container()
            registry = container.get("registry", default=None)
            count = cls.load_pack_routes(registry)
            return {"success": True, "loaded": count}
        except Exception as e:
            _log_internal_error("reload_pack_routes", e)
            return {"success": False, "error": _SAFE_ERROR_MSG, "loaded": 0}
