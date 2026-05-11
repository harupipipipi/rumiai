from __future__ import annotations

from typing import Any

from domain.chat.store import ChatStore
from domain.integrations.store import IntegrationConversationStore


class ExternalConversationResolver:
    def __init__(self, integration_store: IntegrationConversationStore | None = None, chat_store: ChatStore | None = None) -> None:
        self.integration_store = integration_store or IntegrationConversationStore()
        self.chat_store = chat_store or ChatStore()

    def resolve(self, *, provider: str, external_key: str, title: str, metadata: dict[str, Any], model: str | None = None) -> dict[str, Any]:
        return self.integration_store.get_or_create_conversation(
            provider=provider,
            external_key=external_key,
            title=title,
            metadata=metadata,
            chat_store=self.chat_store,
            model=model,
        )
