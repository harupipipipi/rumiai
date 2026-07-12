from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import time
import uuid


class MemorySurface(str, Enum):
    CONVERSATION = "conversation"
    PROJECT = "project"
    USER = "user"
    KNOWLEDGE = "knowledge"
    TYPO = "typo"
    ROMAJI = "romaji"
    RESPONSE_STYLE = "response_style"
    WORK_TYPE = "work_type"
    EMOTION_AGENT = "emotion_agent"


@dataclass
class MemoryEntry:
    surface: str
    key: str
    value: Any
    metadata: Dict[str, Any] = field(default_factory=dict)
    entry_id: str = ""
    created_at: float = 0.0

    def __post_init__(self) -> None:
        if not self.entry_id:
            self.entry_id = uuid.uuid4().hex
        if not self.created_at:
            self.created_at = time.time()


class MemoryManager:
    def __init__(self) -> None:
        self._entries: Dict[str, List[MemoryEntry]] = {}
        self._enabled: Dict[str, bool] = {surface.value: True for surface in MemorySurface}

    def set_surface_enabled(self, surface: str | MemorySurface, enabled: bool) -> None:
        self._enabled[str(surface)] = bool(enabled)

    def store(self, entry: MemoryEntry) -> bool:
        if not self._enabled.get(entry.surface, True):
            return False
        self._entries.setdefault(entry.surface, []).append(entry)
        return True

    def recall(self, surface: str | MemorySurface, key: str) -> List[MemoryEntry]:
        items = self._entries.get(str(surface), [])
        return [entry for entry in items if entry.key == key]

    def list_surface(self, surface: str | MemorySurface) -> List[MemoryEntry]:
        return list(self._entries.get(str(surface), []))
