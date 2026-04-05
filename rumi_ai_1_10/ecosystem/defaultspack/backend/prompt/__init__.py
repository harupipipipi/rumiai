"""
prompt module - Prompt management, rendering, mixing, versioning.

Each prompt has: UUID, icon, metadata, template variables, system prompt.
Prompts can be mixed, previewed, and extended with Python libraries.
"""

from __future__ import annotations

import logging
import threading
import uuid as _uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PromptEntry:
    prompt_id: str
    uuid: str = field(default_factory=lambda: str(_uuid.uuid4()))
    display_name: str = ""
    description: str = ""
    icon: str = ""
    system_prompt: str = ""
    template: str = ""
    variables: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    version: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)
    mix_with: List[str] = field(default_factory=list)
    mix_ai_profile: str = ""
    python_extension: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prompt_id": self.prompt_id,
            "uuid": self.uuid,
            "display_name": self.display_name,
            "description": self.description,
            "icon": self.icon,
            "system_prompt": self.system_prompt,
            "template": self.template,
            "variables": self.variables,
            "tags": self.tags,
            "version": self.version,
            "mix_with": self.mix_with,
        }


class PromptManager:
    """Central prompt registry and renderer."""

    def __init__(self):
        self._lock = threading.RLock()
        self._prompts: Dict[str, PromptEntry] = {}
        self._uuid_index: Dict[str, str] = {}  # uuid -> prompt_id

    def register(self, entry: PromptEntry) -> None:
        with self._lock:
            self._prompts[entry.prompt_id] = entry
            self._uuid_index[entry.uuid] = entry.prompt_id

    def get(self, prompt_id: str) -> Optional[PromptEntry]:
        with self._lock:
            return self._prompts.get(prompt_id)

    def get_by_uuid(self, uuid: str) -> Optional[PromptEntry]:
        with self._lock:
            pid = self._uuid_index.get(uuid)
            return self._prompts.get(pid) if pid else None

    def list_all(self) -> List[PromptEntry]:
        with self._lock:
            return list(self._prompts.values())

    def render(self, prompt_id: str, context: Dict[str, Any] = None) -> str:
        entry = self.get(prompt_id)
        if entry is None:
            return ""
        template = entry.template or entry.system_prompt
        ctx = {**entry.variables, **(context or {})}
        try:
            return template.format(**ctx)
        except (KeyError, IndexError):
            return template

    def mix(self, prompt_ids: List[str], separator: str = "\n\n") -> str:
        parts = []
        for pid in prompt_ids:
            entry = self.get(pid)
            if entry:
                parts.append(entry.system_prompt or entry.template)
        return separator.join(parts)

    def preview_mix(self, prompt_ids: List[str], context: Dict[str, Any] = None) -> str:
        parts = []
        for pid in prompt_ids:
            rendered = self.render(pid, context)
            if rendered:
                parts.append(rendered)
        return "\n\n".join(parts)

    def update(self, prompt_id: str, **kwargs) -> bool:
        with self._lock:
            entry = self._prompts.get(prompt_id)
            if entry is None:
                return False
            for key, value in kwargs.items():
                if hasattr(entry, key):
                    setattr(entry, key, value)
            entry.version += 1
            return True

    def delete(self, prompt_id: str) -> bool:
        with self._lock:
            entry = self._prompts.pop(prompt_id, None)
            if entry:
                self._uuid_index.pop(entry.uuid, None)
                return True
            return False

    def get_metadata_index(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [e.to_dict() for e in self._prompts.values()]
