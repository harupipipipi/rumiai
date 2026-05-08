"""Register UI contract HTTP routes for defaultspack."""

from __future__ import annotations

import os
import sys


def _lazy(module_path: str, func_name: str = "run"):
    def handler(request_data, context):
        import importlib

        mod = importlib.import_module(module_path)
        return getattr(mod, func_name)(request_data, context)

    return handler


def run(context):
    pack_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if pack_root not in sys.path:
        sys.path.insert(0, pack_root)

    interface_registry = context["interface_registry"]
    source_component = context.get("_source_component", "defaultspack:frontend:ui")
    routes = [
        ("GET", "/api/ui/catalog", _lazy("blocks.ui.catalog"), {}),
        ("GET", "/api/ui/settings", _lazy("blocks.ui.settings"), {}),
        ("PUT", "/api/ui/settings", _lazy("blocks.ui.settings"), {}),
        ("GET", "/api/ui/commands", _lazy("blocks.ui.commands"), {}),
        ("POST", "/api/ui/commands/execute", _lazy("blocks.ui.commands"), {}),
        (
            "GET",
            "/api/ui/conversations/{id}/preview",
            _lazy("blocks.ui.conversation_preview"),
            {"id": "conversation_id"},
        ),
    ]

    for method, pattern, handler, path_inject in routes:
        interface_registry.register(
            "io.http.route",
            {
                "method": method,
                "pattern": pattern,
                "handler": handler,
                "path_inject": path_inject,
            },
            meta={"_source_component": source_component},
        )

    return {"status": "ok", "registered": [route[1] for route in routes]}
