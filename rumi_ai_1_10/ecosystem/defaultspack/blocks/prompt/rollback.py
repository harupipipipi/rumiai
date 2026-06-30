from __future__ import annotations

from blocks._common import error, ok
from domain.prompt.editor import PromptWriteConflict, rollback_prompt


def run(input_data: dict, context: dict) -> dict:
    del context
    try:
        return ok(rollback_prompt(input_data))
    except PromptWriteConflict as exc:
        return error(str(exc), "PROMPT_WRITE_CONFLICT")
    except ValueError as exc:
        return error(str(exc), "INVALID_INPUT")
    except Exception as exc:
        return error(str(exc), "PROMPT_ROLLBACK_FAILED")
