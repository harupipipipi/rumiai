from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


class MemoryType(str, Enum):
    CONVERSATION = "conversation"
    PROJECT = "project"
    USER = "user"
    KNOWLEDGE = "knowledge"
    TYPO = "typo"
    ROMAJI = "romaji"
    STYLE = "style"
    WORK_TYPE = "work_type"
    EMOTION = "emotion"


@dataclass
class MemoryEntry:
    memory_id: str
    memory_type: MemoryType
    content: Any
    enabled: bool = True
    updated_at: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.memory_id:
            self.memory_id = str(uuid.uuid4())
        if not self.updated_at:
            self.updated_at = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "memory_type": self.memory_type.value,
            "content": self.content,
            "enabled": self.enabled,
            "updated_at": self.updated_at,
            "metadata": dict(self.metadata),
        }


@dataclass
class UserModel:
    enabled: bool = True
    opt_in: bool = False
    is_hypothesis: bool = True
    preferred_response_style: str = ""
    estimated_work_type: str = ""
    emotion_state: str = "neutral"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "opt_in": self.opt_in,
            "is_hypothesis": self.is_hypothesis,
            "preferred_response_style": self.preferred_response_style,
            "estimated_work_type": self.estimated_work_type,
            "emotion_state": self.emotion_state,
        }


class MemoryStore:
    """Unified memory store supporting all memory types with a common API."""

    def __init__(self, storage_dir: Optional[Path] = None) -> None:
        self._entries: Dict[str, MemoryEntry] = {}
        self._user_model = UserModel()
        self._storage_dir = Path(storage_dir) if storage_dir else None
        self._inference_hooks: List[Callable[[str, UserModel], Dict[str, Any]]] = []

    def store(self, entry: MemoryEntry) -> bool:
        entry.updated_at = time.time()
        self._entries[entry.memory_id] = entry
        return True

    def recall(self, memory_id: str) -> Optional[MemoryEntry]:
        entry = self._entries.get(memory_id)
        if entry and not entry.enabled:
            return None
        return entry

    def search(
        self,
        memory_type: Optional[MemoryType] = None,
        query: Optional[str] = None,
        limit: int = 20,
    ) -> List[MemoryEntry]:
        results = list(self._entries.values())
        if memory_type is not None:
            results = [entry for entry in results if entry.memory_type == memory_type]
        results = [entry for entry in results if entry.enabled]
        if query:
            lowered = query.lower()
            results = [entry for entry in results if lowered in str(entry.content).lower()]
        results.sort(key=lambda entry: entry.updated_at, reverse=True)
        return results[:limit]

    def update(self, memory_id: str, updates: Dict[str, Any]) -> bool:
        entry = self._entries.get(memory_id)
        if entry is None:
            return False
        for key, value in updates.items():
            if hasattr(entry, key):
                setattr(entry, key, value)
        entry.updated_at = time.time()
        return True

    def delete(self, memory_id: str) -> bool:
        return self._entries.pop(memory_id, None) is not None

    def disable(self, memory_id: str) -> bool:
        entry = self._entries.get(memory_id)
        if entry is None:
            return False
        entry.enabled = False
        return True

    def enable(self, memory_id: str) -> bool:
        entry = self._entries.get(memory_id)
        if entry is None:
            return False
        entry.enabled = True
        return True

    def get_user_model(self) -> UserModel:
        return self._user_model

    def update_user_model(self, updates: Dict[str, Any]) -> bool:
        for key, value in updates.items():
            if hasattr(self._user_model, key):
                setattr(self._user_model, key, value)
        return True

    def disable_user_model(self) -> None:
        self._user_model.enabled = False

    def enable_user_model(self) -> None:
        self._user_model.enabled = True

    def register_inference_hook(self, hook: Any) -> None:
        self._inference_hooks.append(hook)

    def run_inference(self, input_text: str) -> Dict[str, Any]:
        results: Dict[str, Any] = {}
        for hook in self._inference_hooks:
            try:
                result = hook(input_text, self._user_model)
                if isinstance(result, dict):
                    results.update(result)
            except Exception:
                continue
        results["is_hypothesis"] = True
        return results

    def save(self) -> None:
        if self._storage_dir is None:
            return
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "entries": {key: entry.to_dict() for key, entry in self._entries.items()},
            "user_model": self._user_model.to_dict(),
        }
        path = self._storage_dir / "memory_store.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)

    def load(self) -> bool:
        if self._storage_dir is None:
            return False
        path = self._storage_dir / "memory_store.json"
        if not path.is_file():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return False
        self._entries.clear()
        for memory_id, entry_data in data.get("entries", {}).items():
            entry_data = dict(entry_data)
            entry_data["memory_type"] = MemoryType(entry_data.get("memory_type", "conversation"))
            self._entries[memory_id] = MemoryEntry(**entry_data)
        user_model = data.get("user_model", {})
        for key, value in user_model.items():
            if hasattr(self._user_model, key):
                setattr(self._user_model, key, value)
        return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_count": len(self._entries),
            "enabled_count": sum(1 for entry in self._entries.values() if entry.enabled),
            "memory_types": sorted({entry.memory_type.value for entry in self._entries.values()}),
            "user_model_enabled": self._user_model.enabled,
            "user_model_opt_in": self._user_model.opt_in,
        }
