"""defaults frontend component setup.

Registers the defaults HTTP server implementation into InterfaceRegistry so
app.py can discover and boot it via the standard ``io.http.server`` interface.
"""

from __future__ import annotations

import os
import sys
import importlib.util
from pathlib import Path


def _load_start_http_server(pack_root: Path, pack_id: str):
    module_path = pack_root / "transport" / "http.py"
    module_name = "rumi_{pack}_transport_http".format(pack=pack_id)
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load transport/http.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module.start_http_server


def run(context: dict | None = None) -> dict:
    context = context or {}
    interface_registry = context.get("interface_registry")
    source_component = context.get("_source_component")
    pack_id = (context.get("ids") or {}).get("pack_id") or "defaults"

    if interface_registry is None:
        raise RuntimeError("interface_registry is required")

    pack_root = Path(__file__).resolve().parents[2]
    pack_root_str = os.fspath(pack_root)
    if pack_root_str not in sys.path:
        sys.path.insert(0, pack_root_str)

    from capability_bindings import register_defaultspack_binding_handlers
    register_defaultspack_binding_handlers(interface_registry)

    start_http_server = _load_start_http_server(pack_root, pack_id)

    interface_registry.register(
        "io.http.server",
        start_http_server,
        meta={
            "owner_pack": pack_id,
            "_source_component": source_component,
        },
    )
    from blocks.ui.setup import run as register_ui_routes
    ui_result = register_ui_routes(
        {
            **context,
            "_source_component": source_component or "defaultspack:frontend:ui",
        }
    )

    return {
        "status": "ok",
        "registered": ["io.http.server", *ui_result.get("registered", [])],
    }
