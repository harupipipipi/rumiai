from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict


def _now_ms() -> int:
    return int(time.time() * 1000)


class IntegrationConversationStore:
    def __init__(self, path: Path | None = None):
        self._path = path or self._default_path()
        self._data = self._load()

    @staticmethod
    def _default_path() -> Path:
        override = os.environ.get("RUMI_DEFAULTSPACK_INTEGRATIONS_STORE_PATH", "").strip()
        if override:
            return Path(override)
        return Path(__file__).resolve().parents[2] / "user_data" / "shared" / "integrations" / "conversations.json"

    def _load(self) -> Dict[str, Any]:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            data = {}
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}
        data.setdefault("schema_version", 1)
        data.setdefault("connections", {})
        data.setdefault("processed_events", {})
        if not isinstance(data.get("connections"), dict):
            data["connections"] = {}
        if not isinstance(data.get("processed_events"), dict):
            data["processed_events"] = {}
        return data

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._data["updated_at"] = _now_ms()
        tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(self._path)

    @staticmethod
    def connection_key(provider: str, external_key: str) -> str:
        return "{}:{}".format(str(provider or "").strip(), str(external_key or "").strip())

    @staticmethod
    def event_key(provider: str, event_id: str) -> str:
        return "{}:{}".format(str(provider or "").strip(), str(event_id or "").strip())

    def is_event_processed(self, provider: str, event_id: str | None) -> bool:
        if not event_id:
            return False
        return self.event_key(provider, event_id) in self._data["processed_events"]

    def mark_event_processed(self, provider: str, event_id: str | None, result: Dict[str, Any]) -> None:
        if not event_id:
            return
        self._data["processed_events"][self.event_key(provider, event_id)] = {
            "provider": provider,
            "event_id": event_id,
            "conversation_id": result.get("conversation_id"),
            "assistant_message_id": result.get("assistant_message_id"),
            "processed_at": _now_ms(),
        }
        self._save()

    def get_or_create_conversation(
        self,
        *,
        provider: str,
        external_key: str,
        title: str,
        metadata: Dict[str, Any],
        chat_store,
        model: str | None = None,
    ) -> Dict[str, Any]:
        key = self.connection_key(provider, external_key)
        existing = self._data["connections"].get(key)
        if isinstance(existing, dict):
            conversation_id = existing.get("conversation_id")
            if conversation_id:
                conversation = chat_store.get_conversation(str(conversation_id))
                if conversation is not None:
                    existing["updated_at"] = _now_ms()
                    self._save()
                    return conversation

        conversation = chat_store.create_conversation(
            model=model,
            conversation_kind="external",
            tags=["integration:" + str(provider or "").strip()],
            metadata={
                "external_provider": provider,
                "external_key": external_key,
                **(metadata if isinstance(metadata, dict) else {}),
            },
        )
        clean_title = str(title or "").strip()[:120] or "{} chat".format(provider)
        conversation = chat_store.update_conversation(conversation["id"], {"title": clean_title}) or conversation
        self._data["connections"][key] = {
            "provider": provider,
            "external_key": external_key,
            "conversation_id": conversation["id"],
            "created_at": _now_ms(),
            "updated_at": _now_ms(),
            "metadata": metadata if isinstance(metadata, dict) else {},
        }
        self._save()
        return conversation
