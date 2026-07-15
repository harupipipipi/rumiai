from __future__ import annotations

from typing import Any

from domain.function_runtime.bridge import invoke_function


def normalize_http_input(input_data: dict[str, Any] | None, context: dict[str, Any] | None) -> dict[str, Any]:
    del context
    return dict(input_data or {})


def function_route(qualified_name: str):
    def run(input_data, context=None):
        args = normalize_http_input(input_data, context)
        return invoke_function(qualified_name, args, context or {}, principal_id="defaultspack")

    return run
