from __future__ import annotations

from pathlib import Path
from typing import Any

from core_runtime.runtime_events import utc_now

from .sqlite_store import default_memory_dir


class MarkdownMemoryStore:
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root is not None else default_memory_dir()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "daily").mkdir(parents=True, exist_ok=True)
        (self.root / "wiki").mkdir(parents=True, exist_ok=True)
        self.ensure_files()

    def ensure_files(self) -> None:
        for name, title in (("MEMORY.md", "Memory"), ("USER.md", "User"), ("DREAMS.md", "Dreams")):
            path = self.root / name
            if not path.exists():
                path.write_text(f"# {title}\n\n", encoding="utf-8")

    def append_memory(self, content: str, metadata: dict[str, Any] | None = None) -> Path:
        return self._append(self.root / "MEMORY.md", content, metadata)

    def append_daily(self, content: str, metadata: dict[str, Any] | None = None) -> Path:
        day = utc_now()[:10]
        return self._append(self.root / "daily" / f"{day}.md", content, metadata)

    def append_user(self, content: str, metadata: dict[str, Any] | None = None) -> Path:
        return self._append(self.root / "USER.md", content, metadata)

    def snapshot(self) -> dict[str, str]:
        result = {}
        for name in ("MEMORY.md", "USER.md", "DREAMS.md"):
            path = self.root / name
            result[name] = path.read_text(encoding="utf-8") if path.exists() else ""
        return result

    @staticmethod
    def _append(path: Path, content: str, metadata: dict[str, Any] | None = None) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        meta = ""
        if metadata:
            meta = " " + " ".join(f"{key}={value}" for key, value in sorted(metadata.items()))
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"- {utc_now()}{meta}: {content}\n")
        return path
