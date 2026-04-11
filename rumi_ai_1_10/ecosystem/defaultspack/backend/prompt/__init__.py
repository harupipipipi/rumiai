"""Prompt management compatibility layer."""

from .prompt_manager import PromptDefinition, PromptEntry, PromptManager, render_template
from .prompt_mixer import PromptMixer

__all__ = [
    "PromptDefinition",
    "PromptEntry",
    "PromptManager",
    "PromptMixer",
    "render_template",
]
