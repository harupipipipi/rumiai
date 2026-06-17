from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from .targeting import ExternalOrigin


def _now_ms() -> int:
    return int(time.time() * 1000)


def external_source_key(provider: str, source_type: str, source_id: str) -> str:
    return ":".join(
        [
            str(provider or "unknown").strip() or "unknown",
            str(source_type or "unknown").strip() or "unknown",
            str(source_id or "unknown").strip() or "unknown",
        ]
    )


class ExternalSourceStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or self._default_path()
        self._data = self._load()

    @staticmethod
    def _default_path() -> Path:
        override = os.environ.get("RUMI_DEFAULTSPACK_EXTERNAL_SOURCES_PATH", "").strip()
        if override:
            return Path(override)
        return Path(__file__).resolve().parents[2] / "user_data" / "shared" / "external_sources.json"

    def list_sources(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self._sources().values()]

    def get(self, provider: str, source_type: str, source_id: str) -> dict[str, Any] | None:
        return self._sources().get(external_source_key(provider, source_type, source_id))

    def is_enabled(self, origin: ExternalOrigin) -> bool:
        item = self.get(origin.provider, origin.source_type, origin.source_id)
        return bool(item and item.get("enabled"))

    def record_origin(self, origin: ExternalOrigin, *, verified: bool) -> dict[str, Any]:
        if not origin.source_id:
            return {"saved": False, "reason": "missing source id"}
        sources = self._sources()
        key = external_source_key(origin.provider, origin.source_type, origin.source_id)
        now = _now_ms()
        current = dict(sources.get(key) or {})
        created = not current
        first_seen = int(current.get("first_seen_at") or now)
        enabled = bool(current.get("enabled", False))
        item = {
            "provider": origin.provider,
            "source_type": origin.source_type,
            "source_id": origin.source_id,
            "actor_last_seen": origin.actor_id,
            "workspace_id": origin.workspace_id,
            "conversation_id": origin.conversation_id,
            "first_seen_at": first_seen,
            "last_seen_at": now,
            "enabled": enabled,
            "allow_reply": bool(current.get("allow_reply", True)),
            "allow_push": bool(current.get("allow_push", False)),
            "label": str(current.get("label") or f"{origin.provider} {origin.source_type} {origin.source_id}"),
            "verified_last_seen": bool(verified),
        }
        for preserved_key in (
            "linked_conversation_id",
            "linked_conversation_title",
            "linked_at",
            "linked_by_actor_id",
        ):
            if current.get(preserved_key) not in (None, ""):
                item[preserved_key] = current[preserved_key]
        sources[key] = item
        self._data["sources"] = sources
        self._save()
        return {"saved": True, "created": created, "key": key, "source": dict(item)}

    def update_source(
        self,
        provider: str,
        source_type: str,
        source_id: str,
        *,
        enabled: bool | None = None,
        allow_reply: bool | None = None,
        allow_push: bool | None = None,
        label: str | None = None,
    ) -> dict[str, Any]:
        key = external_source_key(provider, source_type, source_id)
        sources = self._sources()
        current = dict(sources.get(key) or {})
        if not current:
            return {"success": False, "error": "external source not found", "key": key}
        if enabled is not None:
            current["enabled"] = bool(enabled)
        if allow_reply is not None:
            current["allow_reply"] = bool(allow_reply)
        if allow_push is not None:
            current["allow_push"] = bool(allow_push)
        if label is not None:
            current["label"] = str(label)
        current["updated_at"] = _now_ms()
        sources[key] = current
        self._data["sources"] = sources
        self._save()
        return {"success": True, "key": key, "source": dict(current)}

    def set_linked_conversation(
        self,
        provider: str,
        source_type: str,
        source_id: str,
        conversation_id: str | None,
        *,
        title: str | None = None,
        actor_id: str | None = None,
        enabled: bool | None = None,
    ) -> dict[str, Any]:
        key = external_source_key(provider, source_type, source_id)
        sources = self._sources()
        current = dict(sources.get(key) or {})
        if not current:
            return {"success": False, "error": "external source not found", "key": key}
        cleaned_id = str(conversation_id or "").strip()
        if cleaned_id:
            current["linked_conversation_id"] = cleaned_id
            if title is not None:
                current["linked_conversation_title"] = str(title)
            if actor_id is not None:
                current["linked_by_actor_id"] = str(actor_id)
            current["linked_at"] = _now_ms()
            if enabled is not None:
                current["enabled"] = bool(enabled)
        else:
            for field in (
                "linked_conversation_id",
                "linked_conversation_title",
                "linked_at",
                "linked_by_actor_id",
            ):
                current.pop(field, None)
        current["updated_at"] = _now_ms()
        sources[key] = current
        self._data["sources"] = sources
        self._save()
        return {"success": True, "key": key, "source": dict(current)}

    def _sources(self) -> dict[str, dict[str, Any]]:
        raw = self._data.setdefault("sources", {})
        if not isinstance(raw, dict):
            raw = {}
            self._data["sources"] = raw
        return {str(key): dict(value) for key, value in raw.items() if isinstance(value, dict)}

    def _load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        data.setdefault("schema_version", 1)
        data.setdefault("sources", {})
        return data

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data["updated_at"] = _now_ms()
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.path)
