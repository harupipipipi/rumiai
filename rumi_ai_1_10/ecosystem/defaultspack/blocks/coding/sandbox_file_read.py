from __future__ import annotations

from typing import Any

from blocks._common import error
from blocks.coding.sandbox_common import run_sandbox_action


def run(input_data: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    if not input_data.get("path"):
        return error("'path' is required", code="INVALID_INPUT")
    return run_sandbox_action(
        input_data,
        context,
        lambda manager, workspace: manager.read_file(
            workspace,
            input_data.get("path"),
            start_line=input_data.get("start_line"),
            end_line=input_data.get("end_line"),
            max_chars=input_data.get("max_chars") or input_data.get("max_output_chars"),
        ),
    )
