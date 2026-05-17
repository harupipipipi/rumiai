"""
blocks/vision/setup.py - Vision bridge component setup phase.

Registers structured image-understanding helper routes used by model routing.
"""

import os
import sys


def run(context):
    """Called by the kernel during the setup phase."""
    pack_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if pack_root not in sys.path:
        sys.path.insert(0, pack_root)

    interface_registry = context["interface_registry"]
    source_component = context.get("_source_component", "defaultspack:vision:vision")

    def _lazy(module_path, func_name="run"):
        def handler(request_data, ctx):
            import importlib

            mod = importlib.import_module(module_path)
            fn = getattr(mod, func_name)
            return fn(request_data, ctx)

        return handler

    interface_registry.register(
        "io.http.route",
        {
            "method": "POST",
            "pattern": "/api/vision/describe-images",
            "handler": _lazy("blocks.vision.describe_images"),
            "path_inject": {},
        },
        meta={"_source_component": source_component},
    )
