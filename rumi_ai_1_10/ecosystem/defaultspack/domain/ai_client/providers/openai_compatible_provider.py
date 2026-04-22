import os

from domain.ai_client.providers.openai_provider import OpenAIProvider


class OpenAICompatibleProvider(OpenAIProvider):
    """Configurable OpenAI-compatible provider adapter."""

    KNOWN_MODELS = []

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "",
        known_models=None,
    ):
        super().__init__()
        if api_key:
            self._api_key = api_key
        if base_url:
            self.BASE_URL = base_url.rstrip("/")
        if known_models is not None:
            self.KNOWN_MODELS = list(known_models)
