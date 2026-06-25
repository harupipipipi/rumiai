from __future__ import annotations

from blocks._common import error, ok
from blocks.prompt._model_profiles import with_model_profiles
from domain.prompt.usage import toggle_prompt_edge


def run(input_data: dict, context: dict) -> dict:
    del context
    data = with_model_profiles(input_data if isinstance(input_data, dict) else {})
    try:
        return ok(toggle_prompt_edge(data, preview=True))
    except PermissionError as exc:
        return error(str(exc), "PROMPT_DISABLE_FORBIDDEN")
    except ValueError as exc:
        return error(str(exc), "INVALID_INPUT")
    except Exception as exc:
        return error(str(exc), "PROMPT_PREVIEW_TOGGLE_FAILED")
