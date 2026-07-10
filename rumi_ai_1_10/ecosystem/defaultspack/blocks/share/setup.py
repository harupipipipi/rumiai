"""
blocks/share/setup.py - Share/export component setup phase

Registers share HTTP routes into InterfaceRegistry for the regular
Defaultspack HTTP server path.
"""

import os
import sys


def run(context):
    pack_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if pack_root not in sys.path:
        sys.path.insert(0, pack_root)

    interface_registry = context["interface_registry"]
    source_component = context.get("_source_component", "defaultspack:share:share")

    def _lazy(module_path, func_name="run"):
        def handler(request_data, context):
            import importlib

            mod = importlib.import_module(module_path)
            fn = getattr(mod, func_name)
            return fn(request_data, context)

        return handler

    routes = [
        ("GET", "/api/share", _lazy("blocks.share.list"), {}),
        ("POST", "/api/share", _lazy("blocks.share.create"), {}),
        ("GET", "/api/share/{token}", _lazy("blocks.share.get"), {"token": "token"}),
        ("POST", "/api/share/{token}/export", _lazy("blocks.share.export_bundle"), {"token": "token"}),
        ("POST", "/api/share/{token}/import", _lazy("blocks.share.import_conversation"), {"token": "token"}),
        ("POST", "/api/packs/defaultspack/chat/conversations/import", _lazy("blocks.share.import_bundle"), {}),
        ("DELETE", "/api/share/{token}", _lazy("blocks.share.revoke"), {"token": "token"}),
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
