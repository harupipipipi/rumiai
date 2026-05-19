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
        (self.root / "memos").mkdir(parents=True, exist_ok=True)
        self.ensure_files()
        self.ensure_memo_folder("personalization", title="Personalization")

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

    def ensure_memo_folder(self, slug: str, *, title: str = "") -> Path:
        safe_slug = _safe_path_part(slug or "personalization")
        folder_dir = self.root / "memos" / safe_slug
        folder_dir.mkdir(parents=True, exist_ok=True)
        index_path = folder_dir / "README.md"
        if not index_path.exists():
            index_path.write_text(f"# {title or safe_slug}\n\n", encoding="utf-8")
        return folder_dir

    def write_memo_note(
        self,
        folder_slug: str,
        note_id: str,
        *,
        title: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> Path:
        folder_dir = self.ensure_memo_folder(folder_slug)
        path = folder_dir / f"{_safe_path_part(note_id or 'note')}.md"
        meta = metadata or {}
        frontmatter = ["---"]
        for key, value in sorted(meta.items()):
            frontmatter.append(f"{key}: {value}")
        frontmatter.append("---")
        frontmatter.append("")
        frontmatter.append(f"# {title or 'Untitled memo'}")
        frontmatter.append("")
        frontmatter.append(str(content or "").rstrip())
        frontmatter.append("")
        path.write_text("\n".join(frontmatter), encoding="utf-8")
        return path

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


def _safe_path_part(value: str) -> str:
    text = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in str(value or "").strip())
    text = "-".join(part for part in text.split("-") if part)
    return text[:120] or "memo"
