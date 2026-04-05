"""
stub_provider.py - Stub provider for testing.
"""

from ..base_provider import BaseProvider, CompletionRequest, CompletionResponse, ModelProfile
from typing import Any, List


class StubProvider(BaseProvider):
    def provider_id(self) -> str:
        return "stub"

    def list_models(self) -> List[ModelProfile]:
        return [
            ModelProfile(
                model_id="stub-1",
                provider_id="stub",
                display_name="Stub Model",
                max_tokens=4096,
                context_window=8192,
            ),
        ]

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        return CompletionResponse(
            content="[stub response]",
            model_id="stub-1",
            provider_id="stub",
            finish_reason="stop",
            usage={"input_tokens": 10, "output_tokens": 5},
        )

    def stream(self, request: CompletionRequest) -> Any:
        yield {"content": "[stub", "done": False}
        yield {"content": " response]", "done": True}

    def count_tokens(self, text: str, model_id: str = "") -> int:
        return len(text) // 4
