"""
blocks/knowledge/setup.py - Knowledge component setup phase

Registers knowledge-related HTTP routes into the kernel's InterfaceRegistry
under the key ``io.http.route``.
"""

import sys
import os


def run(context):
    """Called by the kernel during the *setup* phase."""
    pack_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if pack_root not in sys.path:
        sys.path.insert(0, pack_root)

    interface_registry = context["interface_registry"]
    source_component = context.get("_source_component", "defaultspack:knowledge:knowledge")

    def _lazy(module_path, func_name="run"):
        """Return a lazy handler that imports the module on first call."""
        def handler(request_data, context):
            import importlib
            mod = importlib.import_module(module_path)
            fn = getattr(mod, func_name)
            return fn(request_data, context)
        return handler

    routes = [
        ("POST", "/api/packs/defaultspack/knowledge", _lazy("blocks.knowledge.create"), {}),
        ("GET", "/api/packs/defaultspack/knowledge", _lazy("blocks.knowledge.list"), {}),
        ("POST", "/api/packs/defaultspack/knowledge/search", _lazy("blocks.knowledge.search"), {}),
        ("POST", "/api/research/local-search", _lazy("blocks.research.local_search"), {}),
        ("POST", "/api/research/report", _lazy("blocks.research.report"), {}),
        ("GET", "/api/packs/defaultspack/knowledge/{id}", _lazy("blocks.knowledge.get"), {"id": "id"}),
        ("PUT", "/api/packs/defaultspack/knowledge/{id}", _lazy("blocks.knowledge.update"), {"id": "id"}),
        ("DELETE", "/api/packs/defaultspack/knowledge/{id}", _lazy("blocks.knowledge.delete"), {"id": "id"}),
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
