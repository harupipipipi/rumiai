from __future__ import annotations

import json
from pathlib import Path

from .models import ConnectionProvider


class ConnectionsRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, ConnectionProvider] = {}

    def register(self, provider: ConnectionProvider) -> None:
        if provider.provider_id in self._providers:
            raise ValueError(f"Duplicate connection provider: {provider.provider_id}")
        if not provider.display_name:
            raise ValueError(f"Connection provider {provider.provider_id} is missing display name")
        if provider.priority is None:
            raise ValueError(f"Connection provider {provider.provider_id} is missing priority")
        self._providers[provider.provider_id] = provider

    def load_manifest(self, path: str | Path) -> ConnectionProvider:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        provider = ConnectionProvider.from_dict(raw)
        self.register(provider)
        return provider

    def load_manifest_dir(self, root: str | Path) -> None:
        for path in Path(root).rglob("*.connection.json"):
            self.load_manifest(path)

    def get(self, provider_id: str) -> ConnectionProvider:
        try:
            return self._providers[provider_id]
        except KeyError as exc:
            raise KeyError(f"Unknown connection provider: {provider_id}") from exc

    def list_providers(self) -> list[dict]:
        return [provider.to_dict() for provider in sorted(self._providers.values(), key=lambda item: item.priority)]
