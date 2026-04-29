from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any


def _timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class ArtifactStore:
    """Workspace-safe artifact metadata and content store."""

    def __init__(self, pack_root: Path | None = None, workspace_root: Path | None = None) -> None:
        self._pack_root = pack_root or Path(__file__).resolve().parents[2]
        self._workspace_root = (workspace_root or Path.cwd()).resolve()
        self._data_dir = self._pack_root / "user_data" / "shared" / "artifacts"
        self._data_dir.mkdir(parents=True, exist_ok=True)

    def create(
        self,
        *,
        artifact_type: str,
        title: str,
        content: str,
        path: str | None = None,
        created_by: str = "defaultspack",
        source_task: str = "",
    ) -> dict[str, Any]:
        artifact_id = "artifact-" + uuid.uuid4().hex
        target_path = self._resolve_workspace_path(path or f"artifacts/{artifact_id}.md")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(content, encoding="utf-8")
        metadata = {
            "artifact_id": artifact_id,
            "type": artifact_type,
            "title": title,
            "path": str(target_path),
            "content_ref": str(target_path),
            "created_by": created_by,
            "source_task": source_task,
            "version": 1,
            "created_at": _timestamp(),
            "updated_at": _timestamp(),
        }
        self._write_metadata(metadata)
        return metadata

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        items = []
        for path in sorted(self._data_dir.glob("*.json"), reverse=True):
            try:
                items.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
            if len(items) >= limit:
                break
        return items

    def get(self, artifact_id: str) -> dict[str, Any] | None:
        path = self._data_dir / f"{artifact_id}.json"
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def _write_metadata(self, metadata: dict[str, Any]) -> None:
        path = self._data_dir / f"{metadata['artifact_id']}.json"
        path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    def _resolve_workspace_path(self, path: str) -> Path:
        candidate = Path(path)
        resolved = candidate.resolve() if candidate.is_absolute() else (self._workspace_root / candidate).resolve()
        if resolved != self._workspace_root and self._workspace_root not in resolved.parents:
            raise ValueError(f"artifact path escapes workspace: {path}")
        return resolved
