"""
blocks/research/setup.py - Research component setup phase

Registers local and optional external research routes for normal
InterfaceRegistry-backed HTTP startup.
"""

import os
import sys


def run(context):
    pack_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if pack_root not in sys.path:
        sys.path.insert(0, pack_root)

    interface_registry = context["interface_registry"]
    source_component = context.get("_source_component", "defaultspack:research:research")

    def _lazy(module_path, func_name="run"):
        def handler(request_data, context):
            import importlib

            mod = importlib.import_module(module_path)
            fn = getattr(mod, func_name)
            return fn(request_data, context)

        return handler

    routes = [
        ("POST", "/api/research/local-search", _lazy("blocks.research.local_search"), {}),
        ("POST", "/api/research/web-search", _lazy("blocks.research.web_search"), {}),
        ("POST", "/api/research/reddit-search", _lazy("blocks.research.reddit_search"), {}),
        ("POST", "/api/research/report", _lazy("blocks.research.report"), {}),
        ("POST", "/api/research/summary-site", _lazy("blocks.research.summary_site"), {}),
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
