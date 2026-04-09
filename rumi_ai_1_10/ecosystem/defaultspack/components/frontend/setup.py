"""defaults frontend component setup.

Registers the defaults HTTP server implementation into InterfaceRegistry so
app.py can discover and boot it via the standard ``io.http.server`` interface.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


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

    from transport.http import start_http_server

    interface_registry.register(
        "io.http.server",
        start_http_server,
        meta={
            "owner_pack": pack_id,
            "_source_component": source_component,
        },
    )

    return {
        "status": "ok",
        "registered": ["io.http.server"],
    }
