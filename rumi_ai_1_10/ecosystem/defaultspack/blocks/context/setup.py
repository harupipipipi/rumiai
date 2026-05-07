import os
import sys


def run(context):
    pack_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if pack_root not in sys.path:
        sys.path.insert(0, pack_root)
    interface_registry = context["interface_registry"]
    source_component = context.get("_source_component", "defaultspack:context:context")

    def _lazy(module_path, func_name="run"):
        def handler(request_data, context):
            import importlib

            mod = importlib.import_module(module_path)
            return getattr(mod, func_name)(request_data, context)

        return handler

    routes = [
        ("POST", "/api/context/compact", _lazy("blocks.context.compact"), {}),
        ("POST", "/api/context/restore", _lazy("blocks.context.restore"), {}),
        ("POST", "/api/context/token-estimate", _lazy("blocks.context.token_estimate"), {}),
        ("POST", "/api/context/system", _lazy("blocks.context.system"), {}),
        ("POST", "/api/context/conversation", _lazy("blocks.context.conversation"), {}),
    ]
    for method, pattern, handler, path_inject in routes:
        interface_registry.register(
            "io.http.route",
            {"method": method, "pattern": pattern, "handler": handler, "path_inject": path_inject},
            meta={"_source_component": source_component},
        )
