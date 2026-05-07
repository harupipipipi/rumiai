from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class ArtifactStore:
    def __init__(self, pack_root: Optional[Path] = None) -> None:
        self.pack_root = Path(pack_root) if pack_root is not None else Path(__file__).resolve().parents[2]
        self.root = self.pack_root / "user_data" / "artifacts"
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path = self.root / "index.json"

    def _artifact_path(self, user_path: str) -> Path:
        root = self.root.resolve()
        normalized = str(user_path or "").replace("\\", "/").lstrip("/")
        target = (root / normalized).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise ValueError("artifact path escapes artifact root") from exc
        if target == root:
            raise ValueError("artifact path must point to a file")
        return target

    def _load_index(self) -> List[Dict[str, Any]]:
        if not self.index_path.is_file():
            return []
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save_index(self, items: List[Dict[str, Any]]) -> None:
        self.index_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    def create(self, artifact_type: str, title: str, content: str, path: Optional[str] = None, source_task: str = "") -> Dict[str, Any]:
        artifact_id = "artifact_" + str(uuid.uuid4())
        content_path = self._artifact_path(path or artifact_id + ".md")
        safe_name = str(content_path.relative_to(self.root.resolve()))
        content_path.parent.mkdir(parents=True, exist_ok=True)
        content_path.write_text(content, encoding="utf-8")
        item = {
            "artifact_id": artifact_id,
            "type": artifact_type,
            "title": title,
            "path": safe_name,
            "content_ref": content_path.relative_to(self.pack_root).as_posix(),
            "created_by": "defaultspack",
            "source_task": source_task,
            "version": 1,
            "created_at": _ts(),
            "updated_at": _ts(),
        }
        items = self._load_index()
        items.append(item)
        self._save_index(items)
        return item

    def list(self) -> List[Dict[str, Any]]:
        return self._load_index()

    def get(self, artifact_id: str) -> Optional[Dict[str, Any]]:
        for item in self._load_index():
            if item.get("artifact_id") == artifact_id:
                artifact = dict(item)
                content_path = self.pack_root / artifact["content_ref"]
                artifact["content"] = content_path.read_text(encoding="utf-8") if content_path.is_file() else ""
                return artifact
        return None
