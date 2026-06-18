from __future__ import annotations

from blocks._common import error, ok
from domain.prompt.editor import load_prompt_studio


def run(input_data: dict, context: dict) -> dict:
    del context
    data = input_data if isinstance(input_data, dict) else {}
    try:
        return ok(load_prompt_studio(data))
    except ValueError as exc:
        return error(str(exc), "INVALID_INPUT")
    except Exception as exc:
        return error(str(exc), "PROMPT_EDITOR_LOAD_FAILED")
