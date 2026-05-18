from __future__ import annotations

import json
import os
import time
import hashlib
import threading
from pathlib import Path
from typing import Any, Dict


def _now_ms() -> int:
    return int(time.time() * 1000)


class IntegrationConversationStore:
    _LOCKS: dict[str, threading.RLock] = {}
    _LOCKS_GUARD = threading.Lock()

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

    def _reload(self) -> None:
        self._data = self._load()

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._data["updated_at"] = _now_ms()
        tmp_path = self._path.with_name(
            f"{self._path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
        )
        try:
            tmp_path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp_path.replace(self._path)
        finally:
            try:
                tmp_path.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass

    def _path_lock(self) -> threading.RLock:
        try:
            key = str(self._path.resolve())
        except OSError:
            key = str(self._path)
        with self._LOCKS_GUARD:
            lock = self._LOCKS.get(key)
            if lock is None:
                lock = threading.RLock()
                self._LOCKS[key] = lock
            return lock

    @staticmethod
    def connection_key(provider: str, external_key: str) -> str:
        return "{}:{}".format(str(provider or "").strip(), str(external_key or "").strip())

    @staticmethod
    def event_key(provider: str, event_id: str) -> str:
        return "{}:{}".format(str(provider or "").strip(), str(event_id or "").strip())

    @classmethod
    def _event_locks_dir(cls) -> Path:
        override = os.environ.get("RUMI_DEFAULTSPACK_INTEGRATIONS_LOCKS_DIR", "").strip()
        if override:
            return Path(override)
        return cls._default_path().parent / "event_locks"

    @staticmethod
    def _event_lock_ttl_ms() -> int:
        raw = str(os.environ.get("RUMI_DEFAULTSPACK_INTEGRATION_EVENT_LOCK_TTL_MS", "") or "").strip()
        try:
            value = int(raw)
        except Exception:
            value = 30 * 60 * 1000
        return max(value, 1_000)

    @classmethod
    def _event_lock_path(cls, provider: str, event_id: str) -> Path:
        event_key = cls.event_key(provider, event_id)
        digest = hashlib.sha256(event_key.encode("utf-8")).hexdigest()
        return cls._event_locks_dir() / f"{digest}.json"

    @classmethod
    def _prune_stale_event_lock(cls, provider: str, event_id: str) -> bool:
        path = cls._event_lock_path(provider, event_id)
        if not path.exists():
            return False
        try:
            age_ms = _now_ms() - int(path.stat().st_mtime * 1000)
        except OSError:
            age_ms = 0
        if age_ms < cls._event_lock_ttl_ms():
            return False
        try:
            path.unlink()
            return True
        except FileNotFoundError:
            return False
        except OSError:
            return False

    def is_event_processed(self, provider: str, event_id: str | None) -> bool:
        if not event_id:
            return False
        with self._path_lock():
            self._reload()
            return self.event_key(provider, event_id) in self._data["processed_events"]

    def is_event_in_progress(self, provider: str, event_id: str | None) -> bool:
        if not event_id:
            return False
        self._prune_stale_event_lock(provider, event_id)
        return self._event_lock_path(provider, event_id).exists()

    def claim_event(self, provider: str, event_id: str | None, *, metadata: Dict[str, Any] | None = None) -> bool:
        if not event_id:
            return True
        with self._path_lock():
            self._reload()
            if self.event_key(provider, event_id) in self._data["processed_events"]:
                return False
            self._prune_stale_event_lock(provider, event_id)
            path = self._event_lock_path(provider, event_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "provider": provider,
                "event_id": event_id,
                "claimed_at": _now_ms(),
                **(metadata if isinstance(metadata, dict) else {}),
            }
            try:
                fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                return False
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False, indent=2))
            return True

    def release_event_claim(self, provider: str, event_id: str | None) -> None:
        if not event_id:
            return
        try:
            self._event_lock_path(provider, event_id).unlink()
        except FileNotFoundError:
            return
        except OSError:
            return

    def mark_event_processed(self, provider: str, event_id: str | None, result: Dict[str, Any]) -> None:
        if not event_id:
            return
        with self._path_lock():
            self._reload()
            self._data["processed_events"][self.event_key(provider, event_id)] = {
                "provider": provider,
                "event_id": event_id,
                "conversation_id": result.get("conversation_id"),
                "assistant_message_id": result.get("assistant_message_id"),
                "processed_at": _now_ms(),
            }
            self._save()
        self.release_event_claim(provider, event_id)

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
        with self._path_lock():
            self._reload()
            key = self.connection_key(provider, external_key)
            existing = self._data["connections"].get(key)
            if isinstance(existing, dict):
                conversation_id = existing.get("conversation_id")
                if conversation_id:
                    conversation = chat_store.get_conversation(str(conversation_id))
                    if conversation is not None:
                        updates: Dict[str, Any] = {}
                        requested_model = str(model or "").strip()
                        if requested_model and str(conversation.get("model") or "").strip() != requested_model:
                            updates["model"] = requested_model
                        if isinstance(metadata, dict) and metadata:
                            existing_metadata = (
                                conversation.get("metadata") if isinstance(conversation.get("metadata"), dict) else {}
                            )
                            merged_metadata = {**existing_metadata, **metadata}
                            if merged_metadata != existing_metadata:
                                updates["metadata"] = merged_metadata
                        if updates:
                            conversation = chat_store.update_conversation(str(conversation_id), updates) or conversation
                        existing["updated_at"] = _now_ms()
                        if isinstance(metadata, dict) and metadata:
                            existing["metadata"] = {**(existing.get("metadata") if isinstance(existing.get("metadata"), dict) else {}), **metadata}
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
