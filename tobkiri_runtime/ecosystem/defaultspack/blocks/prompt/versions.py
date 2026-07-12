from __future__ import annotations

from blocks._common import error, ok
from domain.prompt.editor import prompt_versions


def run(input_data: dict, context: dict) -> dict:
    del context
    data = input_data if isinstance(input_data, dict) else {}
    try:
        return ok(prompt_versions(data))
    except ValueError as exc:
        return error(str(exc), "INVALID_INPUT")
    except Exception as exc:
        return error(str(exc), "PROMPT_VERSIONS_FAILED")
