"""
base_provider.py - Abstract base for AI providers.

All providers implement this interface. New providers can be added
without modifying the core client code.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional


@dataclass
class ModelProfile:
    """Profile for a specific AI model."""
    model_id: str
    provider_id: str
    display_name: str = ""
    description: str = ""
    icon: str = ""
    max_tokens: int = 4096
    context_window: int = 128000
    supports_streaming: bool = True
    supports_tools: bool = True
    supports_vision: bool = False
    token_cost_per_1k_input: float = 0.0
    token_cost_per_1k_output: float = 0.0
    settings_schema: Dict[str, Any] = field(default_factory=dict)
    advanced_settings: Dict[str, Any] = field(default_factory=dict)
    related_models: List[str] = field(default_factory=list)
    uuid: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "provider_id": self.provider_id,
            "display_name": self.display_name,
            "description": self.description,
            "icon": self.icon,
            "max_tokens": self.max_tokens,
            "context_window": self.context_window,
            "supports_streaming": self.supports_streaming,
            "supports_tools": self.supports_tools,
            "supports_vision": self.supports_vision,
            "uuid": self.uuid,
        }


@dataclass
class CompletionRequest:
    messages: List[Dict[str, Any]]
    model_id: str = ""
    provider_id: str = ""
    max_tokens: int = 4096
    temperature: float = 0.7
    tools: List[Dict[str, Any]] = field(default_factory=list)
    system_prompt: str = ""
    stream: bool = False
    stop_sequences: List[str] = field(default_factory=list)
    thinking_budget: Optional[int] = None


@dataclass
class CompletionResponse:
    content: str = ""
    model_id: str = ""
    provider_id: str = ""
    finish_reason: str = "stop"
    usage: Dict[str, int] = field(default_factory=dict)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    raw_response: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "model_id": self.model_id,
            "provider_id": self.provider_id,
            "finish_reason": self.finish_reason,
            "usage": self.usage,
            "tool_calls": self.tool_calls,
        }


class BaseProvider(abc.ABC):
    """Abstract AI provider interface."""

    @abc.abstractmethod
    def provider_id(self) -> str: ...

    @abc.abstractmethod
    def list_models(self) -> List[ModelProfile]: ...

    @abc.abstractmethod
    def complete(self, request: CompletionRequest) -> CompletionResponse: ...

    @abc.abstractmethod
    def stream(self, request: CompletionRequest) -> Any: ...

    @abc.abstractmethod
    def count_tokens(self, text: str, model_id: str = "") -> int: ...

    def health_check(self) -> bool:
        return True
