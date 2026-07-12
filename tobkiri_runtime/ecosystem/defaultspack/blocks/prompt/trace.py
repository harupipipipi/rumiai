from __future__ import annotations

from blocks._common import error, ok
from domain.prompt.usage import get_prompt_trace, list_prompt_traces


def run(input_data: dict, context: dict) -> dict:
    del context
    data = input_data if isinstance(input_data, dict) else {}
    try:
        if data.get("trace_id") or data.get("id"):
            result = get_prompt_trace(data)
            if result is None:
                return error("Prompt trace not found", "NOT_FOUND")
            return ok(result)
        return ok(list_prompt_traces(data))
    except ValueError as exc:
        return error(str(exc), "INVALID_INPUT")
    except Exception as exc:
        return error(str(exc), "PROMPT_TRACE_FAILED")
