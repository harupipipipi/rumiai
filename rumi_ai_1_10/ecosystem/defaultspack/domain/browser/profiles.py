from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from ._utils import default_browser_root, now_iso, read_json, sanitize_id, write_json


class BrowserProfileManager:
    """Persists managed Chromium profile definitions.

    The profile metadata is intentionally independent from the browser process
    lifecycle so route handlers, tests, and future tool adapters can share it.
    """

    SCHEMA = "managed_chromium"

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root is not None else default_browser_root()
        self.profile_root = self.root / "profiles"
        self.index_path = self.root / "profiles.json"

    def list_profiles(self) -> list[dict[str, Any]]:
        index = self._load_index()
        profiles = index.get("profiles") if isinstance(index.get("profiles"), dict) else {}
        return [self._public_profile(record) for _, record in sorted(profiles.items()) if isinstance(record, dict)]

    def get_profile(self, profile_id: str) -> dict[str, Any]:
        profile_id = sanitize_id(profile_id)
        index = self._load_index()
        profiles = index.get("profiles") if isinstance(index.get("profiles"), dict) else {}
        record = profiles.get(profile_id)
        if not isinstance(record, dict):
            raise KeyError("browser profile not found: {}".format(profile_id))
        return self._public_profile(record)

    def ensure_profile(self, profile_id: str | None = None, **kwargs: Any) -> dict[str, Any]:
        profile_id = sanitize_id(profile_id or kwargs.get("name") or "default")
        try:
            return self.get_profile(profile_id)
        except KeyError:
            return self.create_profile(profile_id=profile_id, **kwargs)

    def create_profile(
        self,
        *,
        profile_id: str | None = None,
        name: str | None = None,
        browser: str = "chromium",
        schema: str = SCHEMA,
        settings: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        set_active: bool = True,
    ) -> dict[str, Any]:
        if schema != self.SCHEMA:
            raise ValueError("unsupported browser profile schema: {}".format(schema))
        profile_id = sanitize_id(profile_id or name or "default")
        index = self._load_index()
        profiles = index.setdefault("profiles", {})
        now = now_iso()
        existing = profiles.get(profile_id) if isinstance(profiles.get(profile_id), dict) else {}
        paths = self._profile_paths(profile_id)
        record: dict[str, Any] = {
            "id": profile_id,
            "schema": schema,
            "kind": schema,
            "name": name or existing.get("name") or profile_id,
            "browser": browser or existing.get("browser") or "chromium",
            "paths": {key: str(value) for key, value in paths.items()},
            "user_data_dir": str(paths["user_data_dir"]),
            "cache_dir": str(paths["cache_dir"]),
            "downloads_dir": str(paths["downloads_dir"]),
            "artifacts_dir": str(paths["artifacts_dir"]),
            "settings": dict(existing.get("settings") or {}),
            "metadata": dict(existing.get("metadata") or {}),
            "created_at": existing.get("created_at") or now,
            "updated_at": now,
        }
        if settings:
            record["settings"].update(settings)
        if metadata:
            record["metadata"].update(metadata)
        record["launch"] = self._launch_schema(record)
        profiles[profile_id] = record
        if set_active or not index.get("active_profile_id"):
            index["active_profile_id"] = profile_id
        index["updated_at"] = now
        self._ensure_profile_dirs(paths)
        self._write_index(index)
        return self._public_profile(record)

    def update_profile(self, profile_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        profile_id = sanitize_id(profile_id)
        index = self._load_index()
        profiles = index.get("profiles") if isinstance(index.get("profiles"), dict) else {}
        record = profiles.get(profile_id)
        if not isinstance(record, dict):
            raise KeyError("browser profile not found: {}".format(profile_id))
        for key in ("name", "browser"):
            if key in updates and updates[key] is not None:
                record[key] = str(updates[key])
        if isinstance(updates.get("settings"), dict):
            settings = dict(record.get("settings") or {})
            settings.update(updates["settings"])
            record["settings"] = settings
        if isinstance(updates.get("metadata"), dict):
            metadata = dict(record.get("metadata") or {})
            metadata.update(updates["metadata"])
            record["metadata"] = metadata
        record["updated_at"] = now_iso()
        record["launch"] = self._launch_schema(record)
        profiles[profile_id] = record
        index["profiles"] = profiles
        index["updated_at"] = record["updated_at"]
        self._write_index(index)
        return self._public_profile(record)

    def delete_profile(self, profile_id: str, *, delete_files: bool = False) -> dict[str, Any]:
        profile_id = sanitize_id(profile_id)
        if profile_id == "default":
            raise ValueError("the default browser profile cannot be deleted")
        index = self._load_index()
        profiles = index.get("profiles") if isinstance(index.get("profiles"), dict) else {}
        existed = profile_id in profiles
        profiles.pop(profile_id, None)
        if index.get("active_profile_id") == profile_id:
            index["active_profile_id"] = "default" if "default" in profiles else None
        index["profiles"] = profiles
        index["updated_at"] = now_iso()
        self._write_index(index)
        if delete_files:
            shutil.rmtree(self.profile_root / profile_id, ignore_errors=True)
        return {"id": profile_id, "deleted": existed, "files_deleted": bool(delete_files)}

    def set_active_profile(self, profile_id: str) -> dict[str, Any]:
        profile = self.get_profile(profile_id)
        index = self._load_index()
        index["active_profile_id"] = profile["id"]
        index["updated_at"] = now_iso()
        self._write_index(index)
        return {"active_profile_id": profile["id"], "profile": profile}

    def get_active_profile_id(self) -> str | None:
        index = self._load_index()
        active = index.get("active_profile_id")
        return str(active) if active else None

    def _profile_paths(self, profile_id: str) -> dict[str, Path]:
        profile_base = self.profile_root / sanitize_id(profile_id)
        return {
            "base_dir": profile_base,
            "user_data_dir": profile_base / "user-data",
            "cache_dir": profile_base / "cache",
            "downloads_dir": profile_base / "downloads",
            "artifacts_dir": profile_base / "artifacts",
        }

    @staticmethod
    def _ensure_profile_dirs(paths: dict[str, Path]) -> None:
        for path in paths.values():
            path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _launch_schema(record: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "managed_chromium",
            "remote_debugging": True,
            "args": [
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-background-networking",
                "--user-data-dir={}".format(record["user_data_dir"]),
                "--disk-cache-dir={}".format(record["cache_dir"]),
            ],
        }

    def _load_index(self) -> dict[str, Any]:
        value = read_json(self.index_path, {})
        if not isinstance(value, dict):
            value = {}
        value.setdefault("version", 1)
        value.setdefault("profiles", {})
        return value

    def _write_index(self, index: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        write_json(self.index_path, index)

    @staticmethod
    def _public_profile(record: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": record.get("id"),
            "schema": record.get("schema", BrowserProfileManager.SCHEMA),
            "kind": record.get("kind", BrowserProfileManager.SCHEMA),
            "name": record.get("name") or record.get("id"),
            "browser": record.get("browser", "chromium"),
            "paths": dict(record.get("paths") or {}),
            "user_data_dir": record.get("user_data_dir"),
            "cache_dir": record.get("cache_dir"),
            "downloads_dir": record.get("downloads_dir"),
            "artifacts_dir": record.get("artifacts_dir"),
            "settings": dict(record.get("settings") or {}),
            "metadata": dict(record.get("metadata") or {}),
            "launch": dict(record.get("launch") or {}),
            "created_at": record.get("created_at"),
            "updated_at": record.get("updated_at"),
        }
