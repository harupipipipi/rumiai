from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from .models import normalize_bundle


class AgentStudioStore:
    _instance = None
    _class_lock = threading.RLock()

    def __new__(cls):
        storage_file = cls._default_storage_file()
        with cls._class_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._lock = threading.RLock()
                cls._instance._storage_file = storage_file
                cls._instance._bundle = cls._instance._load_bundle()
            elif cls._instance._storage_file != storage_file:
                cls._instance._storage_file = storage_file
                cls._instance._bundle = cls._instance._load_bundle()
            return cls._instance

    @staticmethod
    def _default_storage_file() -> Path:
        override = os.environ.get("RUMI_DEFAULTSPACK_AGENT_STUDIO_PATH", "").strip()
        if override:
            path = Path(override)
            return path if path.suffix == ".json" else path / "agent_studio.json"
        return (
            Path(__file__).resolve().parents[2]
            / "user_data"
            / "shared"
            / "agent_studio"
            / "agent_studio.json"
        )

    @property
    def storage_file(self) -> Path:
        return self._storage_file

    def _load_bundle(self) -> dict[str, Any]:
        try:
            payload = json.loads(self._storage_file.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return normalize_bundle({})
        except Exception:
            return normalize_bundle({})
        return normalize_bundle(payload)

    def _atomic_write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            dir=str(path.parent),
            prefix="." + path.name + ".",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            Path(tmp_name).replace(path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    def _save(self) -> None:
        self._bundle = normalize_bundle(self._bundle)
        self._atomic_write_json(self._storage_file, self._bundle)

    def read(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._bundle)

    def replace(self, bundle: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._bundle = normalize_bundle(bundle)
            self._save()
            return copy.deepcopy(self._bundle)

    def update_settings(self, updates: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            current = self.read()
            current["settings"] = {
                **current.get("settings", {}),
                **copy.deepcopy(updates or {}),
            }
            self._bundle = normalize_bundle(current)
            self._save()
            return copy.deepcopy(self._bundle["settings"])

    def upsert_profile(self, record: dict[str, Any]) -> dict[str, Any]:
        from .models import normalize_registered_profile

        with self._lock:
            item = normalize_registered_profile(record)
            self._bundle.setdefault("profiles", {})[item["id"]] = item
            self._save()
            return copy.deepcopy(item)

    def delete_profile(self, profile_id: str) -> bool:
        with self._lock:
            if text := str(profile_id or "").strip():
                removed = self._bundle.setdefault("profiles", {}).pop(text, None)
                if removed is not None:
                    self._save()
                    return True
            return False

    def upsert_team(self, record: dict[str, Any]) -> dict[str, Any]:
        from .models import normalize_team_definition

        with self._lock:
            item = normalize_team_definition(record)
            self._bundle.setdefault("teams", {})[item["id"]] = item
            self._save()
            return copy.deepcopy(item)

    def delete_team(self, team_id: str) -> bool:
        with self._lock:
            if text := str(team_id or "").strip():
                removed = self._bundle.setdefault("teams", {}).pop(text, None)
                if removed is not None:
                    self._save()
                    return True
            return False

    def upsert_fusion(self, record: dict[str, Any]) -> dict[str, Any]:
        from .models import normalize_fusion_definition

        with self._lock:
            item = normalize_fusion_definition(record)
            self._bundle.setdefault("fusions", {})[item["id"]] = item
            self._save()
            return copy.deepcopy(item)

    def delete_fusion(self, fusion_id: str) -> bool:
        with self._lock:
            if text := str(fusion_id or "").strip():
                removed = self._bundle.setdefault("fusions", {}).pop(text, None)
                if removed is not None:
                    self._save()
                    return True
            return False

    def replace_selection_rules(self, rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
        from .models import normalize_selection_rule

        with self._lock:
            self._bundle["selection_rules"] = [
                normalize_selection_rule(rule) for rule in rules if isinstance(rule, dict)
            ]
            self._save()
            return copy.deepcopy(self._bundle["selection_rules"])
