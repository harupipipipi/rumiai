"""Compatibility shim for the canonical PromptBuilder implementation."""

from core_runtime.prompt_builder import PromptBuilder as _CorePromptBuilder
from core_runtime.prompt_builder import evaluate_condition


def _prompt_template_factory(**kwargs):
    from .template import PromptTemplate

    return PromptTemplate(**kwargs)


def _prompt_manager_factory():
    from .manager import get_manager

    return get_manager()


def _render(template, variables=None):
    from .renderer import render

    return render(template, variables)


PromptBuilder = _CorePromptBuilder.with_dependencies(
    prompt_template_factory=_prompt_template_factory,
    prompt_manager_factory=_prompt_manager_factory,
    render_func=_render,
)

__all__ = ["PromptBuilder", "evaluate_condition"]
