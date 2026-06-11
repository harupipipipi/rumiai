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

    def _lazy_with_defaults(module_path, defaults, func_name="run"):
        handler = _lazy(module_path, func_name)

        def wrapped(request_data, context):
            payload = {**request_data, **defaults}
            return handler(payload, context)

        return wrapped

    routes = [
        # --- 既存ルート ---
        ("GET", "/api/system-prompts", _lazy("blocks.prompt.system_profiles"), {}),
        ("POST", "/api/system-prompts", _lazy("blocks.prompt.system_profiles"), {}),
        ("PUT", "/api/system-prompts/{prompt_id}", _lazy("blocks.prompt.system_profiles"), {"prompt_id": "prompt_id"}),
        ("DELETE", "/api/system-prompts/{prompt_id}", _lazy("blocks.prompt.system_profiles"), {"prompt_id": "prompt_id"}),
        ("POST", "/api/system-prompts/{prompt_id}/activate", _lazy_with_defaults("blocks.prompt.system_profiles", {"action": "activate"}), {"prompt_id": "prompt_id"}),
        ("PUT", "/api/prompts/{name}", _lazy("blocks.prompt.update"), {"name": "name"}),
        ("DELETE", "/api/prompts/{name}", _lazy("blocks.prompt.delete"), {"name": "name"}),
        ("POST", "/api/prompts/convert", _lazy("blocks.prompt.convert"), {}),
        ("POST", "/api/prompts/lint", _lazy("blocks.prompt.lint_prompt"), {}),
        ("POST", "/api/prompts/compact", _lazy("blocks.prompt.compact_prompt"), {}),
        # --- advanced ルート ---
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
