from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from .api_response import APIResponse


logger = logging.getLogger(__name__)


class WebMountMixin:
    @classmethod
    def load_web_mounts(cls, registry, pack_ids: Optional[set[str]] = None) -> int:
        cls._web_mounts = []
        if registry is None:
            return 0
        count = 0
        for pack_id, pack_info in registry.packs.items():
            if pack_ids is not None and pack_id not in pack_ids:
                continue
            wm = pack_info.ecosystem.get("web_mount")
            if not wm or not isinstance(wm, dict):
                continue
            path_prefix = wm.get("path_prefix", "")
            static_root_rel = wm.get("static_root", "")
            if not path_prefix or not static_root_rel:
                continue
            base_dir = getattr(pack_info, "subdir", None) or pack_info.path
            web_root = Path(str(base_dir)) / static_root_rel
            cls._web_mounts.append(
                {
                    "path_prefix": path_prefix,
                    "web_root": web_root.resolve(),
                    "spa_fallback": wm.get("spa_fallback", False),
                    "auth_required": wm.get("auth_required", True),
                    "pack_id": pack_id,
                }
            )
            count += 1
        cls._web_mounts.sort(key=lambda e: len(e["path_prefix"]), reverse=True)
        logger.info("Loaded %d web_mount entries", count)
        return count

    @classmethod
    def load_pre_auth_routes(cls, registry, pack_ids: Optional[set[str]] = None) -> int:
        cls._pre_auth_table = []
        if registry is None:
            return 0
        count = 0
        for pack_id, pack_info in registry.packs.items():
            if pack_ids is not None and pack_id not in pack_ids:
                continue
            routes = pack_info.ecosystem.get("pre_auth_routes")
            if routes and isinstance(routes, list):
                for route in routes:
                    if not isinstance(route, dict):
                        continue
                    method = route.get("method", "").upper()
                    if not method:
                        continue
                    entry = {"method": method, "pack_id": pack_id}
                    if "path" in route:
                        entry["path"] = route["path"]
                    if "path_prefix" in route:
                        entry["path_prefix"] = route["path_prefix"]
                    cls._pre_auth_table.append(entry)
                    count += 1
            wm = pack_info.ecosystem.get("web_mount")
            if wm and isinstance(wm, dict) and not wm.get("auth_required", True):
                prefix = wm.get("path_prefix", "")
                if prefix:
                    for method in ("GET", "POST", "PUT", "DELETE"):
                        cls._pre_auth_table.append(
                            {
                                "method": method,
                                "path_prefix": prefix,
                                "pack_id": pack_id,
                                "_source": "web_mount",
                            }
                        )
                    count += 4
        logger.info("Loaded %d pre_auth_route entries", count)
        return count

    def _match_web_mount(self, request_path: str):
        for wm in self._web_mounts:
            prefix = wm["path_prefix"]
            if request_path == prefix or request_path.startswith(prefix + "/"):
                return wm
        fallback_mounts = {
            "/panel": {
                "web_root": Path(__file__).resolve().parent.parent / "core_pack" / "core_control_panel" / "web",
                "spa_fallback": True,
                "index_file": "index.html",
                "auth_required": True,
                "pack_id": "core_control_panel",
            },
            "/setup": {
                "web_root": Path(__file__).resolve().parent.parent / "core_pack" / "core_setup" / "web",
                "spa_fallback": True,
                "index_file": "index.html",
                "auth_required": False,
                "pack_id": "core_setup",
            },
        }
        for prefix, mount in fallback_mounts.items():
            if request_path == prefix or request_path.startswith(prefix + "/"):
                return {"path_prefix": prefix, **mount}
        return None

    _MIME_TYPES = {
        ".html": "text/html; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".svg": "image/svg+xml",
        ".ico": "image/x-icon",
        ".woff": "font/woff",
        ".woff2": "font/woff2",
        ".ttf": "font/ttf",
        ".map": "application/json",
    }

    def _serve_static_file(
        self,
        request_path: str,
        _wm: Optional[dict[str, Any]] = None,
    ) -> None:
        if _wm is None:
            _wm = self._match_web_mount(request_path)
        if _wm is None:
            self._send_response(APIResponse(False, error="Not found"), 404)
            return

        path_prefix = _wm["path_prefix"]
        web_root = _wm["web_root"]
        spa_fallback = _wm.get("spa_fallback", False)
        index_file = _wm.get("index_file", "index.html")

        sub_path = request_path[len(path_prefix):]
        if not sub_path or sub_path == "/":
            sub_path = "/" + index_file
        try:
            target = (web_root / sub_path.lstrip("/")).resolve()
            target.relative_to(web_root.resolve())
        except (ValueError, OSError):
            self._send_response(APIResponse(False, error="Forbidden"), 403)
            return

        if not target.is_file():
            index_fallback = web_root / index_file
            if spa_fallback and index_fallback.is_file() and "." not in target.name:
                target = index_fallback
            else:
                self._send_response(APIResponse(False, error="Not found"), 404)
                return

        content_type = self._MIME_TYPES.get(target.suffix.lower(), "application/octet-stream")
        try:
            data = target.read_bytes()
        except OSError:
            self._send_response(APIResponse(False, error="Read error"), 500)
            return

        try:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            origin = self._get_cors_origin(self.headers.get("Origin", ""))
            if origin:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
            self.end_headers()
            self.wfile.write(data)
        except self._CLIENT_DISCONNECT_EXCEPTIONS:
            self.close_connection = True
