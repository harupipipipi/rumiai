"""Provider abstractions for the defaultspack AI client slice."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional, Sequence


@dataclass
class CompletionRequest:
    messages: List[Dict[str, Any]] = field(default_factory=list)
    model: str = ""
    temperature: float = 0.7
    max_tokens: int = 4096
    stop: Optional[List[str]] = None
    tools: Optional[List[Dict[str, Any]]] = None
    stream: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CompletionResponse:
    content: str = ""
    finish_reason: str = ""
    model: str = ""
    usage: Dict[str, int] = field(default_factory=dict)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    raw: Optional[Any] = None


@dataclass
class StreamChunk:
    delta: str = ""
    finish_reason: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None


@dataclass
class RetryPolicy:
    max_retries: int = 3
    backoff_seconds: float = 1.5
    wait_seconds: float = 1.5
    failover_providers: List[str] = field(default_factory=list)
    retryable_errors: List[str] = field(default_factory=list)
    tool_fallback: Optional[str] = None
    on_error: str = "retry"
    notify_user: bool = True
    output_cause: bool = True

    def __post_init__(self) -> None:
        if self.wait_seconds == 1.5 and self.backoff_seconds != 1.5:
            self.wait_seconds = self.backoff_seconds
        if self.backoff_seconds == 1.5 and self.wait_seconds != 1.5:
            self.backoff_seconds = self.wait_seconds

    def should_retry(self, attempt: int, error: Optional[str] = None) -> bool:
        if attempt >= self.max_retries:
            return False
        if not error:
            return True
        if not self.retryable_errors:
            return True
        return any(token in error for token in self.retryable_errors)


@dataclass
class ProviderConfig:
    provider_id: str = ""
    display_name: str = ""
    description: str = ""
    default_model: str = ""
    models: List[str] = field(default_factory=list)
    settings: Dict[str, Any] = field(default_factory=dict)
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)


class ProviderAdapter:
    """Base class for provider adapters."""

    def __init__(self, config: Optional[ProviderConfig] = None) -> None:
        self.config = config or ProviderConfig()
        self.provider_id = self.config.provider_id

    @property
    def display_name(self) -> str:
        return self.config.display_name or self.provider_id

    def list_models(self) -> List[str]:
        return list(self.config.models)

    def token_count(self, value: Any, model: str = "") -> int:
        if isinstance(value, str):
            return max(0, len(value) // 4)
        if isinstance(value, CompletionRequest):
            messages = value.messages
        elif isinstance(value, Sequence):
            messages = list(value)
        else:
            messages = []
        total = 0
        for message in messages:
            if isinstance(message, dict):
                content = message.get("content", "")
                if isinstance(content, str):
                    total += max(0, len(content) // 4)
        return total

    def count_tokens(self, value: Any, model: str = "") -> int:
        return self.token_count(value, model=model)

    def model_uuid(self, model_name: str) -> str:
        from uuid import NAMESPACE_DNS, uuid5

        return str(uuid5(NAMESPACE_DNS, f"{self.provider_id}:{model_name}"))

    def request(self, request: Any, model: str = "", **kwargs: Any) -> Any:
        if type(self).invoke is ProviderAdapter.invoke:
            raise NotImplementedError
        try:
            return self.invoke(request, model=model, **kwargs)
        except TypeError:
            return self.invoke(request, **kwargs)

    def invoke(self, request: Any, **kwargs: Any) -> Any:
        if type(self).request is ProviderAdapter.request:
            raise NotImplementedError
        try:
            return self.request(request, **kwargs)
        except TypeError:
            model = kwargs.pop("model", "")
            return self.request(request, model=model, **kwargs)

    def complete(self, request: Any, **kwargs: Any) -> Any:
        return self.invoke(request, **kwargs)

    def stream(self, request: Any, **kwargs: Any) -> Iterator[Any]:
        yield self.invoke(request, **kwargs)

    def stop(self, request_id: str) -> bool:
        return False

    def health_check(self) -> bool:
        return True


BaseProvider = ProviderAdapter
