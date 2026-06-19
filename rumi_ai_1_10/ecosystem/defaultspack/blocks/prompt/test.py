from __future__ import annotations

from blocks._common import error, ok
from domain.prompt.editor import test_prompt_input
from domain.skill_trigger import RuntimeSkillTriggerService
from domain.templates.tool_policy_resolution import resolve_template_tool_policy


def _runtime_skill_evaluator(
    *,
    skills: list[dict] | None,
    user_text: str,
    selected_tools: list[str],
    context: dict,
) -> dict:
    return RuntimeSkillTriggerService(skills).evaluate(
        user_text=user_text,
        tool_names=selected_tools,
        context=context,
    )


def _template_tool_policy_resolver(
    *,
    template_policy: dict | None,
    metadata: dict | None,
) -> dict:
    resolution = resolve_template_tool_policy(template_policy, metadata=metadata)
    context = resolution.to_context()
    context["policy"] = resolution.policy
    return context


def run(input_data: dict, context: dict) -> dict:
    del context
    try:
        return ok(
            test_prompt_input(
                input_data,
                skill_evaluator=_runtime_skill_evaluator,
                template_policy_resolver=_template_tool_policy_resolver,
            )
        )
    except ValueError as exc:
        return error(str(exc), "INVALID_INPUT")
    except Exception as exc:
        return error(str(exc), "PROMPT_TEST_FAILED")
