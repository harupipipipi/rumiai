"""Coding component setup routes."""

import os
import sys


def run(context):
    pack_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if pack_root not in sys.path:
        sys.path.insert(0, pack_root)

    interface_registry = context["interface_registry"]
    source_component = context.get("_source_component", "defaultspack:coding:coding")

    def _lazy(module_path, func_name="run"):
        def handler(request_data, ctx):
            import importlib

            mod = importlib.import_module(module_path)
            return getattr(mod, func_name)(request_data, ctx)

        return handler

    routes = [
        ("GET", "/api/coding/context", _lazy("blocks.coding.context"), {}),
        ("POST", "/api/coding/files/read", _lazy("blocks.coding.file_read"), {}),
        ("POST", "/api/coding/files/write", _lazy("blocks.coding.file_write"), {}),
        ("POST", "/api/coding/files/create", _lazy("blocks.coding.file_create"), {}),
        ("POST", "/api/coding/files/delete", _lazy("blocks.coding.file_delete"), {}),
        ("GET", "/api/coding/files", _lazy("blocks.coding.file_list"), {}),
        ("POST", "/api/coding/files/search", _lazy("blocks.coding.file_search"), {}),
        ("POST", "/api/coding/terminal/exec", _lazy("blocks.coding.terminal_exec"), {}),
        ("POST", "/api/coding/terminal/stream", _lazy("blocks.coding.terminal_stream"), {}),
        ("GET", "/api/coding/git/status", _lazy("blocks.coding.git_status"), {}),
        ("GET", "/api/coding/git/diff", _lazy("blocks.coding.git_diff"), {}),
        ("GET", "/api/coding/git/branch", _lazy("blocks.coding.git_branch"), {}),
        ("POST", "/api/coding/git/branch", _lazy("blocks.coding.git_branch"), {}),
        ("POST", "/api/coding/git/commit", _lazy("blocks.coding.git_commit"), {}),
        ("POST", "/api/coding/git/push", _lazy("blocks.coding.git_push"), {}),
    ]

    for method, pattern, handler, path_inject in routes:
        interface_registry.register(
            "io.http.route",
            {"method": method, "pattern": pattern, "handler": handler, "path_inject": path_inject},
            meta={"_source_component": source_component},
        )
