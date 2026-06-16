from __future__ import annotations

from blocks._common import error, ok
from domain.prompt.usage import toggle_prompt_edge


def run(input_data: dict, context: dict) -> dict:
    del context
    data = input_data if isinstance(input_data, dict) else {}
    preview = bool(data.get("preview") or data.get("_preview"))
    try:
        return ok(toggle_prompt_edge(data, preview=preview))
    except PermissionError as exc:
        return error(str(exc), "PROMPT_DISABLE_FORBIDDEN")
    except ValueError as exc:
        return error(str(exc), "INVALID_INPUT")
    except Exception as exc:
        return error(str(exc), "PROMPT_TOGGLE_FAILED")
