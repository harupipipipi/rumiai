import os
import sys


def run(context):
    pack_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if pack_root not in sys.path:
        sys.path.insert(0, pack_root)
    interface_registry = context["interface_registry"]
    source_component = context.get("_source_component", "defaultspack:gateway:gateway")

    def _lazy(module_path, func_name="run"):
        def handler(request_data, context):
            import importlib

            mod = importlib.import_module(module_path)
            return getattr(mod, func_name)(request_data, context)

        return handler

    routes = [
        ("GET", "/api/defaultspack/gateway/status", _lazy("blocks.gateway.status"), {}),
        ("POST", "/api/defaultspack/gateway/start", _lazy("blocks.gateway.start"), {}),
        ("POST", "/api/defaultspack/gateway/stop", _lazy("blocks.gateway.stop"), {}),
        ("POST", "/api/defaultspack/gateway/send", _lazy("blocks.gateway.send"), {}),
        ("POST", "/api/defaultspack/gateway/pairing", _lazy("blocks.gateway.pairing"), {}),
    ]
    for method, pattern, handler, path_inject in routes:
        interface_registry.register(
            "io.http.route",
            {"method": method, "pattern": pattern, "handler": handler, "path_inject": path_inject},
            meta={"_source_component": source_component},
        )
