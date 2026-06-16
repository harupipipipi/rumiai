from __future__ import annotations

from blocks._common import error, ok
from domain.prompt.usage import active_prompt_summary


def run(input_data: dict, context: dict) -> dict:
    del context
    try:
        return ok(active_prompt_summary(input_data))
    except Exception as exc:
        return error(str(exc), "PROMPT_ACTIVE_FAILED")
