from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .context import adaptive_store_root, clean_profile_id


class AdaptiveStore:
    def __init__(self, profile_id: str, root: Path | None = None) -> None:
        self.profile_id = clean_profile_id(profile_id)
        self.root = Path(root).resolve() if root is not None else adaptive_store_root(self.profile_id)

    def read_json(self, relative_path: str, default: Any) -> Any:
        path = self._path(relative_path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return default
        return data

    def write_json(self, relative_path: str, payload: Any) -> Any:
        path = self._path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        tmp.replace(path)
        return payload

    def append_jsonl(self, relative_path: str, payload: dict[str, Any]) -> dict[str, Any]:
        path = self._path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str) + "\n")
        return payload

    def read_jsonl(self, relative_path: str, *, limit: int | None = None) -> list[dict[str, Any]]:
        path = self._path(relative_path)
        rows: list[dict[str, Any]] = []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (FileNotFoundError, OSError):
            return []
        if limit is not None and limit >= 0:
            lines = lines[-limit:]
        for line in lines:
            if not line.strip():
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                rows.append(parsed)
        return rows

    def _path(self, relative_path: str) -> Path:
        candidate = (self.root / relative_path).resolve()
        root = self.root.resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError("adaptive store path escaped profile root") from exc
        return candidate
