"""
blocks/prompt/setup.py - Prompt component setup phase

Registers prompt-related HTTP routes into the kernel's InterfaceRegistry
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
    source_component = context.get("_source_component", "defaultspack:prompt:prompt")

    def _lazy(module_path, func_name="run"):
        """Return a lazy handler that imports the module on first call."""
        def handler(request_data, context):
            import importlib
            mod = importlib.import_module(module_path)
            fn = getattr(mod, func_name)
            return fn(request_data, context)
        return handler

    routes = [
        # --- prompt workspace routes ---
        ("GET", "/api/prompts", _lazy("blocks.prompt.editor"), {}),
        ("GET", "/api/prompts/active", _lazy("blocks.prompt.active"), {}),
        ("GET", "/api/prompts/traces", _lazy("blocks.prompt.trace"), {}),
        ("GET", "/api/prompts/traces/{trace_id}", _lazy("blocks.prompt.trace"), {"trace_id": "trace_id"}),
        ("POST", "/api/prompts/toggle", _lazy("blocks.prompt.toggle"), {}),
        ("POST", "/api/prompts/preview-toggle", _lazy("blocks.prompt.toggle"), {"_preview": "_preview"}),
        ("GET", "/api/prompts/editor", _lazy("blocks.prompt.editor"), {}),
        ("POST", "/api/prompts/editor/save", _lazy("blocks.prompt.editor"), {}),
        ("POST", "/api/prompts/override", _lazy("blocks.prompt.editor"), {}),
        ("POST", "/api/prompts/diff", _lazy("blocks.prompt.diff"), {}),
        ("POST", "/api/prompts/test", _lazy("blocks.prompt.test"), {}),
        ("POST", "/api/prompts/{name}/rollback", _lazy("blocks.prompt.rollback"), {"name": "name"}),
        # --- existing routes ---
        ("PUT", "/api/prompts/{name}", _lazy("blocks.prompt.update"), {"name": "name"}),
        ("DELETE", "/api/prompts/{name}", _lazy("blocks.prompt.delete"), {"name": "name"}),
        ("POST", "/api/prompts/convert", _lazy("blocks.prompt.convert"), {}),
        ("POST", "/api/prompts/lint", _lazy("blocks.prompt.lint_prompt"), {}),
        ("POST", "/api/prompts/compact", _lazy("blocks.prompt.compact_prompt"), {}),
        # --- prompt control/editor routes ---
        ("POST", "/api/prompts/control", _lazy("blocks.prompt.control"), {}),
        ("POST", "/api/prompts/editor", _lazy("blocks.prompt.control"), {}),
        # --- advanced routes ---
        ("POST", "/api/prompts/build", _lazy("blocks.prompt.advanced.build"), {}),
        ("GET", "/api/prompts/context-vars", _lazy("blocks.prompt.advanced.context_vars"), {}),
        ("POST", "/api/prompts/{name}/conditional", _lazy("blocks.prompt.advanced.conditional"), {"name": "name"}),
        ("POST", "/api/prompts/{name}/inherit", _lazy("blocks.prompt.advanced.inherit"), {"name": "name"}),
        ("GET", "/api/prompts/{name}/versions", _lazy("blocks.prompt.advanced.version"), {"name": "name"}),
        ("POST", "/api/prompts/{name}/versions", _lazy("blocks.prompt.advanced.version"), {"name": "name"}),
        ("PUT", "/api/prompts/{name}/versions/{version}", _lazy("blocks.prompt.advanced.version"), {"name": "name", "version": "version"}),
        ("POST", "/api/prompts/preview", _lazy("blocks.prompt.advanced.preview"), {}),
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
