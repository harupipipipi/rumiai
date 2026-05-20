"""Register Memory2 memo HTTP routes."""

from __future__ import annotations

import importlib


def run(context):
    interface_registry = context["interface_registry"]
    source_component = context.get("_source_component", "defaultspack:memory:memory")

    def _lazy(module_path):
        def handler(request_data, request_context):
            return getattr(importlib.import_module(module_path), "run")(request_data, request_context)

        return handler

    routes = [
        ("GET", "/api/memory/memo/folders", _lazy("blocks.memory.memo_folders"), {}),
        ("POST", "/api/memory/memo/folders", _lazy("blocks.memory.memo_folders"), {}),
        ("GET", "/api/memory/memo/folders/{id}", _lazy("blocks.memory.memo_folders"), {"id": "folder_id"}),
        ("PUT", "/api/memory/memo/folders/{id}", _lazy("blocks.memory.memo_folders"), {"id": "folder_id"}),
        ("DELETE", "/api/memory/memo/folders/{id}", _lazy("blocks.memory.memo_folders"), {"id": "folder_id"}),
        ("GET", "/api/memory/memo/notes", _lazy("blocks.memory.memo_notes"), {}),
        ("POST", "/api/memory/memo/notes", _lazy("blocks.memory.memo_notes"), {}),
        ("GET", "/api/memory/memo/notes/{id}", _lazy("blocks.memory.memo_notes"), {"id": "note_id"}),
        ("PUT", "/api/memory/memo/notes/{id}", _lazy("blocks.memory.memo_notes"), {"id": "note_id"}),
        ("DELETE", "/api/memory/memo/notes/{id}", _lazy("blocks.memory.memo_notes"), {"id": "note_id"}),
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
