"""
blocks/dev/setup.py - Dev component setup phase

Registers dev-tool HTTP routes into the kernel's InterfaceRegistry
under the key ``io.http.route``.

Also registers CLI config API routes:
  - GET  /api/cli/config → blocks.cli.entry (run_get)
  - PUT  /api/cli/config → blocks.cli.entry (run_put)
"""

import sys
import os


def run(context):
    """Called by the kernel during the *setup* phase."""
    pack_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if pack_root not in sys.path:
        sys.path.insert(0, pack_root)

    interface_registry = context["interface_registry"]
    source_component = context.get("_source_component", "defaultspack:dev:dev")

    def _lazy(module_path, func_name="run"):
        """Return a lazy handler that imports the module on first call."""
        def handler(request_data, context):
            import importlib
            mod = importlib.import_module(module_path)
            fn = getattr(mod, func_name)
            return fn(request_data, context)
        return handler

    routes = [
        ("GET", "/api/dev/inspect", _lazy("blocks.dev.inspect"), {}),
        ("GET", "/api/dev/prompt-history", _lazy("blocks.dev.prompt_history"), {}),
        ("POST", "/api/dev/edit-prompt", _lazy("blocks.dev.edit_prompt_live"), {}),
        ("POST", "/api/dev/replay", _lazy("blocks.dev.replay"), {}),
        ("GET", "/api/dev/agent-runs", _lazy("blocks.dev.agent_runs"), {}),
        ("GET", "/api/dev/agent-runs/{id}", _lazy("blocks.dev.agent_runs"), {"id": "run_id"}),
        ("GET", "/api/dev/agent-runs/{id}/events", _lazy("blocks.dev.agent_run_events"), {"id": "run_id"}),
        ("GET", "/api/dev/agent-runs/{id}/transcript", _lazy("blocks.dev.agent_run_transcript"), {"id": "run_id"}),
        ("GET", "/api/dev/compactions", _lazy("blocks.dev.compactions"), {}),
        ("GET", "/api/dev/memory", _lazy("blocks.dev.memory"), {}),
        ("GET", "/api/dev/scheduler", _lazy("blocks.dev.scheduler"), {}),
        ("GET", "/api/dev/tool-ledger", _lazy("blocks.dev.tool_ledger"), {}),
        # ── CLI config API routes ──
        ("GET", "/api/cli/config", _lazy("blocks.cli.entry", "run_get"), {}),
        ("PUT", "/api/cli/config", _lazy("blocks.cli.entry", "run_put"), {}),
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
