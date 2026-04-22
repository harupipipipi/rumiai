from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..extensions.loading import import_entrypoint
from ..extensions.runtime import get_extension_registry


class KnowledgeBackendRegistry:
    """Manifest-driven knowledge backend lookup."""

    def __init__(self) -> None:
        self._registry = get_extension_registry().knowledge_backends()

    def list_backends(self) -> List[Dict[str, Any]]:
        return self._registry.list(enabled_only=True)

    def get_backend(self, backend_id: str) -> Optional[Dict[str, Any]]:
        return self._registry.get(backend_id)

    def create_backend(self, backend_id: str) -> Any:
        manifest = self.get_backend(backend_id)
        if manifest is None:
            raise KeyError(f"knowledge backend not found: {backend_id}")
        entrypoint = str(manifest.get("entrypoint", "")).strip()
        if not entrypoint:
            raise ValueError(f"knowledge backend has no entrypoint: {backend_id}")
        backend_cls = import_entrypoint(entrypoint)
        return backend_cls()
