"""Register Rumi Review change-request HTTP routes for defaultspack."""

from __future__ import annotations

import importlib
import os
import sys
from typing import Any


def run(context: dict[str, Any]):
    pack_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if pack_root not in sys.path:
        sys.path.insert(0, pack_root)

    interface_registry = context["interface_registry"]
    source_component = context.get("_source_component", "defaultspack:change_request:change_request")

    routes = [
        ("GET", "/api/change-requests", "blocks.change_request.collection", {}),
        ("POST", "/api/change-requests", "blocks.change_request.collection", {}),
        ("GET", "/api/change-requests/{id}", "blocks.change_request.item", {"id": "id"}),
        ("PATCH", "/api/change-requests/{id}", "blocks.change_request.item", {"id": "id"}),
        ("POST", "/api/change-requests/{id}/refresh", "blocks.change_request.refresh", {"id": "id"}),
        (
            "POST",
            "/api/change-requests/{id}/export-patch",
            "blocks.change_request.export_patch",
            {"id": "id"},
        ),
    ]

    for method, pattern, module_path, path_inject in routes:
        interface_registry.register(
            "io.http.route",
            {
                "method": method,
                "pattern": pattern,
                "handler": _lazy_handler(module_path),
                "path_inject": path_inject,
            },
            meta={"_source_component": source_component},
        )

    return {"status": "ok", "registered": [route[1] for route in routes]}


def _lazy_handler(module_path: str):
    def handler(request_data, context):
        module = importlib.import_module(module_path)
        return module.run(request_data, context)

    return handler
