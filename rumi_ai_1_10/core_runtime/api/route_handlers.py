"""Pack 独自ルート ハンドラ Mixin"""
from __future__ import annotations

import logging
from urllib.parse import unquote

from ._helpers import _log_internal_error, _SAFE_ERROR_MSG

logger = logging.getLogger(__name__)


def _is_safe_path_param(value: str) -> bool:
    """パスパラメータが安全かどうかを検証する。

    null バイトやパストラバーサルシーケンスを含む値を拒否する。
    """
    if "\x00" in value:
        return False
    if ".." in value:
        return False
    return True


class RouteHandlersMixin:
    """Pack 独自ルート (load / match / handle / reload) のハンドラ"""

    _pack_routes: dict = {}  # {(method, path): route_info}

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
                method = route.get("method", "GET").upper()
                path = route.get("path", "")
                if not path:
                    continue
                flow_id = route.get("flow_id", "")
                if not flow_id:
                    continue

                route_info = {
                    "pack_id": pack_id,
                    "flow_id": flow_id,
                    "description": route.get("description", ""),
                    "input_mapping": route.get("input_mapping", {}),
                }

                # テンプレートセグメント解析
                segments = path.strip("/").split("/")
                param_indices = {}
                for i, seg in enumerate(segments):
                    if seg.startswith("{") and seg.endswith("}"):
                        param_name = seg[1:-1]
                        param_indices[i] = param_name

                if param_indices:
                    route_info["_segments"] = segments
                    route_info["_param_indices"] = param_indices
                else:
                    route_info["_segments"] = None
                    route_info["_param_indices"] = {}

                cls._pack_routes[(method, path)] = route_info
                count += 1
                logger.debug(
                    "Registered pack route: %s %s -> %s/%s",
                    method, path, pack_id, flow_id,
                )

        logger.info("Loaded %d pack routes", count)
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
                continue
            path_params = {}
            matched = True
            for i, (tmpl_seg, req_seg) in enumerate(zip(tmpl_segments, request_segments)):
                if i in param_indices:
                    decoded = unquote(req_seg)
                    if not _is_safe_path_param(decoded):
                        matched = False
                        break
                    path_params[param_indices[i]] = decoded
                elif tmpl_seg != req_seg:
                    matched = False
                    break
            if matched:
                return (route_info, path_params)

        return None

    def _handle_pack_route_request(self, path: str, body: dict, method: str, match) -> None:
        """Pack独自ルートへのリクエストをFlow実行に委譲する"""
        from ..pack_api_server import APIResponse

        route_info, path_params = match
        pack_id = route_info["pack_id"]
        flow_id = route_info["flow_id"]

        # Flow スコープ検証: flow_id は当該 Pack のスコープ内でなければならない
        if not (flow_id.startswith(pack_id + ".") or flow_id == pack_id):
            logger.warning(
                "Flow scope violation: pack_id=%s, flow_id=%s", pack_id, flow_id,
            )
            self._send_response(
                APIResponse(False, error="Flow scope violation"), 403,
            )
            return

        input_mapping = route_info.get("input_mapping", {})

        # 入力を構築
        inputs = {}
        if body and isinstance(body, dict):
            inputs.update(body)
        if path_params:
            inputs["_path_params"] = path_params
        inputs["_method"] = method
        inputs["_path"] = path

        # input_mapping を適用
        if input_mapping and isinstance(input_mapping, dict):
            for target_key, source_expr in input_mapping.items():
                if isinstance(source_expr, str) and source_expr.startswith("path."):
                    param_name = source_expr[5:]
                    if param_name in path_params:
                        inputs[target_key] = path_params[param_name]

        result = self._run_flow(flow_id, inputs, timeout=300)
        if result.get("success"):
            self._send_response(APIResponse(True, result))
        else:
            status_code = result.get("status_code", 500)
            self._send_response(
                APIResponse(False, error=result.get("error")), status_code,
            )

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
