from __future__ import annotations

from blocks._common import error, ok
from domain.prompt.editor import test_prompt_input


def run(input_data: dict, context: dict) -> dict:
    del context
    try:
        return ok(test_prompt_input(input_data))
    except ValueError as exc:
        return error(str(exc), "INVALID_INPUT")
    except Exception as exc:
        return error(str(exc), "PROMPT_TEST_FAILED")
