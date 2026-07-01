from __future__ import annotations

from blocks._common import error, ok
from blocks.prompt._model_profiles import with_model_profiles
from domain.prompt.editor import (
    compact_prompt_text,
    create_profile_override,
    diff_prompt,
    lint_prompt_text,
    load_prompt_studio,
    PromptWriteConflict,
    prompt_versions,
    rollback_prompt,
    save_prompt,
    test_prompt_input,
)


def run(input_data: dict, context: dict) -> dict:
    del context
    data = with_model_profiles(input_data if isinstance(input_data, dict) else {})
    action = str(data.get("action") or "load").strip().lower()
    try:
        if action == "load":
            return ok(load_prompt_studio(data))
        if action == "save":
            return ok(save_prompt(data))
        if action in {"override", "create_override"}:
            return ok(create_profile_override(data))
        if action == "diff":
            return ok(diff_prompt(data))
        if action in {"versions", "version_list"}:
            return ok(prompt_versions(data))
        if action == "rollback":
            return ok(rollback_prompt(data))
        if action == "lint":
            return ok(lint_prompt_text(data))
        if action == "compact":
            return ok(compact_prompt_text(data))
        if action in {"test", "test_input", "studio_test"}:
            return ok(test_prompt_input(data))
        return error(f"Unknown prompt editor action: {action}", "INVALID_INPUT")
    except PromptWriteConflict as exc:
        return error(str(exc), "PROMPT_WRITE_CONFLICT")
    except ValueError as exc:
        return error(str(exc), "INVALID_INPUT")
    except Exception as exc:
        return error(str(exc), "PROMPT_EDITOR_FAILED")
