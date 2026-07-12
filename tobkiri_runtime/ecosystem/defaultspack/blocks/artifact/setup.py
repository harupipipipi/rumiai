"""
blocks/artifact/setup.py - Artifact component setup phase

Registers artifact HTTP routes into the kernel's InterfaceRegistry under the
key ``io.http.route`` so normal Defaultspack startup does not rely on fallback
transport routes.
"""

import os
import sys


def run(context):
    pack_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if pack_root not in sys.path:
        sys.path.insert(0, pack_root)

    interface_registry = context["interface_registry"]
    source_component = context.get("_source_component", "defaultspack:artifact:artifact")

    def _lazy(module_path, func_name="run"):
        def handler(request_data, context):
            import importlib

            mod = importlib.import_module(module_path)
            fn = getattr(mod, func_name)
            return fn(request_data, context)

        return handler

    routes = [
        ("GET", "/api/artifacts", _lazy("blocks.artifact.list"), {}),
        ("POST", "/api/artifacts", _lazy("blocks.artifact.create"), {}),
        ("GET", "/api/artifacts/{id}", _lazy("blocks.artifact.get"), {"id": "artifact_id"}),
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
