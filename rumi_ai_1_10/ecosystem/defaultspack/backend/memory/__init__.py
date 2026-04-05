"""
memory module - Multi-type memory management.

Types: conversation, project, user, knowledge, typo tendency,
romaji tendency, response style, work type estimation, personality.
"""

from __future__ import annotations
import logging, threading, time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

class MemoryType:
    CONVERSATION = "conversation"
    PROJECT = "project"
    USER = "user"
    KNOWLEDGE = "knowledge"
    TYPO_TENDENCY = "typo_tendency"
    ROMAJI_TENDENCY = "romaji_tendency"
    RESPONSE_STYLE = "response_style"
    WORK_TYPE = "work_type"
    PERSONALITY = "personality"
    EMOTION = "emotion"
    ALL = [CONVERSATION, PROJECT, USER, KNOWLEDGE, TYPO_TENDENCY,
           ROMAJI_TENDENCY, RESPONSE_STYLE, WORK_TYPE, PERSONALITY, EMOTION]

@dataclass
class MemoryEntry:
    memory_id: str
    memory_type: str
    content: Any
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    confidence: float = 1.0
    is_hypothesis: bool = False
    enabled: bool = True
    def to_dict(self) -> Dict[str, Any]:
        return {"memory_id": self.memory_id, "memory_type": self.memory_type,
                "content": self.content, "confidence": self.confidence,
                "is_hypothesis": self.is_hypothesis, "enabled": self.enabled}

class MemoryManager:
    def __init__(self):
        self._lock = threading.RLock()
        self._stores: Dict[str, Dict[str, MemoryEntry]] = {t: {} for t in MemoryType.ALL}
        self._enabled_types: set = set(MemoryType.ALL)

    def store(self, entry: MemoryEntry) -> None:
        with self._lock:
            if entry.memory_type not in self._enabled_types: return
            self._stores.setdefault(entry.memory_type, {})[entry.memory_id] = entry

    def recall(self, memory_type: str, memory_id: str) -> Optional[MemoryEntry]:
        with self._lock:
            e = self._stores.get(memory_type, {}).get(memory_id)
            return e if e and e.enabled else None

    def search(self, memory_type: str, query: str, limit: int = 10) -> List[MemoryEntry]:
        with self._lock:
            q = query.lower()
            return [e for e in self._stores.get(memory_type, {}).values()
                    if e.enabled and q in str(e.content).lower()][:limit]

    def update(self, memory_type: str, memory_id: str, content: Any, **kw) -> bool:
        with self._lock:
            e = self._stores.get(memory_type, {}).get(memory_id)
            if not e: return False
            e.content = content; e.updated_at = time.time()
            for k, v in kw.items():
                if hasattr(e, k): setattr(e, k, v)
            return True

    def delete(self, memory_type: str, memory_id: str) -> bool:
        with self._lock: return self._stores.get(memory_type, {}).pop(memory_id, None) is not None

    def disable_entry(self, memory_type: str, memory_id: str) -> bool:
        with self._lock:
            e = self._stores.get(memory_type, {}).get(memory_id)
            if e: e.enabled = False; return True
            return False

    def enable_type(self, t: str) -> None: self._enabled_types.add(t)
    def disable_type(self, t: str) -> None: self._enabled_types.discard(t)
    def list_types(self) -> Dict[str, bool]: return {t: t in self._enabled_types for t in MemoryType.ALL}

    def store_hypothesis(self, memory_type: str, mid: str, content: Any, confidence: float = 0.5) -> None:
        self.store(MemoryEntry(memory_id=mid, memory_type=memory_type, content=content,
                               confidence=confidence, is_hypothesis=True))

    def get_user_model(self) -> Dict[str, Any]:
        model = {}
        for mt in [MemoryType.TYPO_TENDENCY, MemoryType.ROMAJI_TENDENCY,
                    MemoryType.RESPONSE_STYLE, MemoryType.WORK_TYPE, MemoryType.PERSONALITY]:
            entries = [e.to_dict() for e in self._stores.get(mt, {}).values() if e.enabled]
            if entries: model[mt] = entries
        return model
