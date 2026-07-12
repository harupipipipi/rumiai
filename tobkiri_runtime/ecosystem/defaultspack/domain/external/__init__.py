"""Extensible external input and response framework."""

from .event import ExternalEvent
from .principal import ExternalPrincipal

__all__ = [
    "ExternalEvent",
    "ExternalPrincipal",
]

try:
    from .response_prompt_policy import (
        ResponsePromptDecision,
        ResponsePromptPolicy,
        decide_response_prompt,
    )
except ModuleNotFoundError:
    # Some utility callers import submodules such as input_profile_registry
    # without wiring the legacy `domain.*` package alias used by response
    # policy modules. Keep those imports working by making the policy symbols
    # optional at package import time.
    pass
else:
    __all__.extend(
        [
            "ResponsePromptDecision",
            "ResponsePromptPolicy",
            "decide_response_prompt",
        ]
    )
