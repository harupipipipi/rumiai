"""Prompt management compatibility layer."""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "PromptDefinition",
    "PromptEntry",
    "PromptManager",
    "PromptMixer",
    "render_template",
]

_EXPORTS = {
    "PromptDefinition": ("prompt_manager", "PromptDefinition"),
    "PromptEntry": ("prompt_manager", "PromptEntry"),
    "PromptManager": ("prompt_manager", "PromptManager"),
    "PromptMixer": ("prompt_mixer", "PromptMixer"),
    "render_template": ("prompt_manager", "render_template"),
}

_MODULE_PREFIXES = (
    __name__,
    "ecosystem.defaultspack.backend.prompt",
    "tobkiri_runtime.ecosystem.defaultspack.backend.prompt",
)


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attr_name = _EXPORTS[name]
    last_error = None
    for prefix in _MODULE_PREFIXES:
        try:
            module = import_module(f"{prefix}.{module_name}")
            value = getattr(module, attr_name)
            globals()[name] = value
            return value
        except (ImportError, AttributeError) as exc:
            last_error = exc

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from last_error
