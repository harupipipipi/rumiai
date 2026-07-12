"""
blocks/cli/setup.py — CLI component setup phase.

Registers:
  - io.cli.server into InterfaceRegistry (for kernel launch)
  - CLI config HTTP routes into io.http.route
"""

import sys
import os


def run(context):
    """Called by the kernel during the *setup* phase."""
    pack_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if pack_root not in sys.path:
        sys.path.insert(0, pack_root)

    interface_registry = context["interface_registry"]
    source_component = context.get("_source_component", "defaults:cli:cli")

    # ================================================================
    # 1. io.cli.server 登録
    # ================================================================
    try:
        from transport.cli import start_cli_server
    except Exception as exc:
        print(
            "[defaults.cli] setup: failed to import transport.cli – "
            + str(exc),
            file=sys.stderr,
        )
        return

    try:
        interface_registry.register(
            "io.cli.server",
            start_cli_server,
            meta={
                "_source_component": source_component,
                "description": "CLI server provided by defaults pack",
            },
        )
    except Exception as exc:
        print(
            "[defaults.cli] setup: failed to register io.cli.server – "
            + str(exc),
            file=sys.stderr,
        )

    # ================================================================
    # 2. io.http.route 登録 (CLI config API)
    # ================================================================
    def _lazy(module_path, func_name="run"):
        """Return a lazy handler that imports the module on first call."""
        def handler(request_data, ctx):
            import importlib
            mod = importlib.import_module(module_path)
            fn = getattr(mod, func_name)
            return fn(request_data, ctx)
        return handler

    routes = [
        ("GET", "/api/cli/config", _lazy("blocks.cli.entry", "run_get"), {}),
        ("PUT", "/api/cli/config", _lazy("blocks.cli.entry", "run_put"), {}),
    ]

    for method, pattern, handler, path_inject in routes:
        try:
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
        except Exception as exc:
            print(
                "[defaults.cli] setup: failed to register route "
                + method + " " + pattern + " – " + str(exc),
                file=sys.stderr,
            )
