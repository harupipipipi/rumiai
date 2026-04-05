"""
supporter module - AI support services (summarization, analysis, etc.).
"""

from __future__ import annotations
from typing import Any, Dict


class SupporterManager:
    def __init__(self):
        self._supporters = {}

    def register(self, name: str, handler: Any) -> None:
        self._supporters[name] = handler

    def invoke(self, name: str, data: Dict[str, Any] = None) -> Dict[str, Any]:
        handler = self._supporters.get(name)
        if handler is None:
            return {"error": f"Supporter '{name}' not found"}
        try:
            return {"result": handler(data or {})}
        except Exception as exc:
            return {"error": str(exc)}

    def list_all(self) -> list:
        return list(self._supporters.keys())
