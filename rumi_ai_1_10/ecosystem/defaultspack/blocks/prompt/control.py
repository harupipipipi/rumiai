from __future__ import annotations

from blocks._common import ok


def run(input_data: dict, context: dict) -> dict:
    del input_data, context
    return ok({"ready": True})
