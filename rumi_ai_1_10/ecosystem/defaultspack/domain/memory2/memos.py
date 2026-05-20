from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from blocks._common import gen_id
from core_runtime.runtime_audit_helpers import redact_sensitive
from core_runtime.runtime_events import utc_now

from .markdown_store import MarkdownMemoryStore
from .sqlite_store import MemorySQLiteStore


DEFAULT_PERSONALIZATION_FOLDER_ID = "personalization"
DEFAULT_PERSONALIZATION_FOLDER_NAME = "Personalization"

_SLUG_RE = re.compile(r"[^a-z0-9_-]+")


class MemoStore:
    """Durable memo folders and notes backed by Memory2 SQLite + Markdown."""

    def __init__(
        self,
        sqlite_store: MemorySQLiteStore | None = None,
        markdown_store: MarkdownMemoryStore | None = None,
    ) -> None:
        self.sqlite = sqlite_store or MemorySQLiteStore()
        self.markdown = markdown_store or MarkdownMemoryStore(self.sqlite.root)
        self.ensure_default_folders()

    def ensure_default_folders(self) -> dict[str, Any]:
        folder = self.get_folder(DEFAULT_PERSONALIZATION_FOLDER_ID)
        if folder is not None:
            return folder
        return self.create_folder(
            DEFAULT_PERSONALIZATION_FOLDER_NAME,
            folder_id=DEFAULT_PERSONALIZATION_FOLDER_ID,
            slug=DEFAULT_PERSONALIZATION_FOLDER_ID,
            description="Default folder for stable user preferences and personalization notes.",
            metadata={"default": True, "kind": "personalization"},
        )

    def create_folder(
        self,
        name: str,
        *,
        folder_id: str | None = None,
        slug: str | None = None,
        description: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        clean_name = str(name or "").strip()
        if not clean_name:
            raise ValueError("folder name is required")
        folder_slug = _slug(slug or clean_name)
        now = utc_now()
        folder = {
            "id": folder_id or gen_id("memo_folder_"),
            "name": clean_name,
            "slug": folder_slug,
            "description": str(description or "").strip(),
            "metadata": redact_sensitive(metadata or {}),
            "created_at": now,
            "updated_at": now,
            "archived_at": None,
        }
        with self.sqlite.conn:
            self.sqlite.conn.execute(
                """
                INSERT INTO memo_folders(id, name, slug, description, metadata_json, created_at, updated_at, archived_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  name=excluded.name,
                  slug=excluded.slug,
                  description=excluded.description,
                  metadata_json=excluded.metadata_json,
                  updated_at=excluded.updated_at,
                  archived_at=excluded.archived_at
                """,
                (
                    folder["id"],
                    folder["name"],
                    folder["slug"],
                    folder["description"],
                    self.sqlite.json_dumps(folder["metadata"]),
                    folder["created_at"],
                    folder["updated_at"],
                    folder["archived_at"],
                ),
            )
        self.markdown.ensure_memo_folder(folder["slug"], title=folder["name"])
        return folder

    def list_folders(self, *, include_archived: bool = False) -> list[dict[str, Any]]:
        where = "" if include_archived else "WHERE archived_at IS NULL"
        rows = self.sqlite.conn.execute(
            f"SELECT * FROM memo_folders {where} ORDER BY name COLLATE NOCASE ASC"
        ).fetchall()
        return [self._folder_from_row(row) for row in rows]

    def get_folder(self, folder_id_or_slug: str) -> dict[str, Any] | None:
        key = str(folder_id_or_slug or "").strip()
        if not key:
            return None
        row = self.sqlite.conn.execute(
            "SELECT * FROM memo_folders WHERE (id = ? OR slug = ?) AND archived_at IS NULL",
            (key, key),
        ).fetchone()
        return self._folder_from_row(row) if row else None

    def update_folder(self, folder_id_or_slug: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        current = self.get_folder(folder_id_or_slug)
        if current is None:
            return None
        merged = dict(current)
        if "name" in updates:
            name = str(updates.get("name") or "").strip()
            if name:
                merged["name"] = name
        if "description" in updates:
            merged["description"] = str(updates.get("description") or "").strip()
        if "slug" in updates:
            merged["slug"] = _slug(updates.get("slug") or merged["name"])
        if isinstance(updates.get("metadata"), dict):
            merged["metadata"] = redact_sensitive({**merged.get("metadata", {}), **updates["metadata"]})
        merged["updated_at"] = utc_now()
        with self.sqlite.conn:
            self.sqlite.conn.execute(
                """
                UPDATE memo_folders
                SET name = ?, slug = ?, description = ?, metadata_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    merged["name"],
                    merged["slug"],
                    merged["description"],
                    self.sqlite.json_dumps(merged.get("metadata", {})),
                    merged["updated_at"],
                    merged["id"],
                ),
            )
        self.markdown.ensure_memo_folder(merged["slug"], title=merged["name"])
        return merged

    def delete_folder(self, folder_id_or_slug: str, *, archive_notes: bool = True) -> bool:
        folder = self.get_folder(folder_id_or_slug)
        if folder is None:
            return False
        if folder["id"] == DEFAULT_PERSONALIZATION_FOLDER_ID:
            raise ValueError("default personalization folder cannot be deleted")
        now = utc_now()
        with self.sqlite.conn:
            self.sqlite.conn.execute(
                "UPDATE memo_folders SET archived_at = ?, updated_at = ? WHERE id = ?",
                (now, now, folder["id"]),
            )
            if archive_notes:
                self.sqlite.conn.execute(
                    "UPDATE memo_notes SET archived_at = ?, updated_at = ? WHERE folder_id = ? AND archived_at IS NULL",
                    (now, now, folder["id"]),
                )
        return True

    def create_note(
        self,
        content: str,
        *,
        title: str = "",
        folder_id: str = DEFAULT_PERSONALIZATION_FOLDER_ID,
        metadata: dict[str, Any] | None = None,
        source: str = "manual",
        note_id: str | None = None,
    ) -> dict[str, Any]:
        clean_content = str(content or "").strip()
        if not clean_content:
            raise ValueError("note content is required")
        folder_key = str(folder_id or DEFAULT_PERSONALIZATION_FOLDER_ID).strip() or DEFAULT_PERSONALIZATION_FOLDER_ID
        folder = self.get_folder(folder_key)
        if folder is None and folder_key != DEFAULT_PERSONALIZATION_FOLDER_ID:
            raise ValueError("memo folder not found")
        folder = folder or self.ensure_default_folders()
        clean_title = str(title or "").strip() or _title_from_content(clean_content)
        now = utc_now()
        note = {
            "id": note_id or gen_id("memo_note_"),
            "folder_id": folder["id"],
            "folder_slug": folder["slug"],
            "title": clean_title,
            "content": str(redact_sensitive(clean_content)),
            "metadata": redact_sensitive(metadata or {}),
            "source": str(source or "manual").strip() or "manual",
            "created_at": now,
            "updated_at": now,
            "archived_at": None,
        }
        with self.sqlite.conn:
            self.sqlite.conn.execute(
                """
                INSERT INTO memo_notes(
                  id, folder_id, title, content, metadata_json, source, created_at, updated_at, archived_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  folder_id=excluded.folder_id,
                  title=excluded.title,
                  content=excluded.content,
                  metadata_json=excluded.metadata_json,
                  source=excluded.source,
                  updated_at=excluded.updated_at,
                  archived_at=excluded.archived_at
                """,
                (
                    note["id"],
                    note["folder_id"],
                    note["title"],
                    note["content"],
                    self.sqlite.json_dumps(note["metadata"]),
                    note["source"],
                    note["created_at"],
                    note["updated_at"],
                    note["archived_at"],
                ),
            )
        markdown_path = self.markdown.write_memo_note(
            folder["slug"],
            note["id"],
            title=note["title"],
            content=note["content"],
            metadata={"folder_id": folder["id"], "source": note["source"], **note["metadata"]},
        )
        note["markdown_path"] = str(markdown_path)
        return note

    def get_note(self, note_id: str) -> dict[str, Any] | None:
        key = str(note_id or "").strip()
        if not key:
            return None
        row = self.sqlite.conn.execute(
            """
            SELECT n.*, f.slug AS folder_slug
            FROM memo_notes n
            LEFT JOIN memo_folders f ON f.id = n.folder_id
            WHERE n.id = ? AND n.archived_at IS NULL
            """,
            (key,),
        ).fetchone()
        return self._note_from_row(row) if row else None

    def list_notes(
        self,
        *,
        folder_id: str | None = None,
        limit: int = 50,
        include_archived: bool = False,
    ) -> list[dict[str, Any]]:
        params: list[Any] = []
        where = []
        if not include_archived:
            where.append("n.archived_at IS NULL")
        if folder_id:
            folder = self.get_folder(folder_id)
            if folder is None:
                return []
            where.append("n.folder_id = ?")
            params.append(folder["id"])
        sql = """
            SELECT n.*, f.slug AS folder_slug
            FROM memo_notes n
            LEFT JOIN memo_folders f ON f.id = n.folder_id
        """
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY n.updated_at DESC LIMIT ?"
        params.append(max(1, int(limit or 50)))
        rows = self.sqlite.conn.execute(sql, params).fetchall()
        return [self._note_from_row(row) for row in rows]

    def search_notes(
        self,
        query: str,
        *,
        folder_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        text = str(query or "").strip()
        params: list[Any] = []
        where = ["n.archived_at IS NULL"]
        if folder_id:
            folder = self.get_folder(folder_id)
            if folder is None:
                return []
            where.append("n.folder_id = ?")
            params.append(folder["id"])
        if text:
            where.append("(n.title LIKE ? OR n.content LIKE ? OR n.metadata_json LIKE ?)")
            needle = f"%{text}%"
            params.extend([needle, needle, needle])
        sql = """
            SELECT n.*, f.slug AS folder_slug
            FROM memo_notes n
            LEFT JOIN memo_folders f ON f.id = n.folder_id
            WHERE """ + " AND ".join(where) + " ORDER BY n.updated_at DESC LIMIT ?"
        params.append(max(1, int(limit or 20)))
        rows = self.sqlite.conn.execute(sql, params).fetchall()
        results = [self._note_from_row(row) for row in rows]
        for result in results:
            result["score"] = _score(text, result.get("title", "") + "\n" + result.get("content", ""))
        results.sort(key=lambda item: item.get("score", 0), reverse=True)
        return results

    def update_note(self, note_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        current = self.get_note(note_id)
        if current is None:
            return None
        folder_id = str(updates.get("folder_id") or updates.get("folder") or current["folder_id"])
        folder = self.get_folder(folder_id)
        if folder is None:
            raise ValueError("memo folder not found")
        merged = dict(current)
        merged["folder_id"] = folder["id"]
        merged["folder_slug"] = folder["slug"]
        if "title" in updates:
            title = str(updates.get("title") or "").strip()
            if title:
                merged["title"] = title
        if "content" in updates:
            content = str(updates.get("content") or "").strip()
            if content:
                merged["content"] = str(redact_sensitive(content))
        if isinstance(updates.get("metadata"), dict):
            merged["metadata"] = redact_sensitive({**merged.get("metadata", {}), **updates["metadata"]})
        if "source" in updates:
            merged["source"] = str(updates.get("source") or merged.get("source") or "manual").strip() or "manual"
        merged["updated_at"] = utc_now()
        with self.sqlite.conn:
            self.sqlite.conn.execute(
                """
                UPDATE memo_notes
                SET folder_id = ?, title = ?, content = ?, metadata_json = ?, source = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    merged["folder_id"],
                    merged["title"],
                    merged["content"],
                    self.sqlite.json_dumps(merged.get("metadata", {})),
                    merged.get("source", "manual"),
                    merged["updated_at"],
                    merged["id"],
                ),
            )
        markdown_path = self.markdown.write_memo_note(
            folder["slug"],
            merged["id"],
            title=merged["title"],
            content=merged["content"],
            metadata={"folder_id": folder["id"], "source": merged.get("source", "manual"), **merged.get("metadata", {})},
        )
        merged["markdown_path"] = str(markdown_path)
        return merged

    def delete_note(self, note_id: str) -> bool:
        now = utc_now()
        with self.sqlite.conn:
            cur = self.sqlite.conn.execute(
                "UPDATE memo_notes SET archived_at = ?, updated_at = ? WHERE id = ? AND archived_at IS NULL",
                (now, now, str(note_id or "").strip()),
            )
        return cur.rowcount > 0

    def _folder_from_row(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        data["metadata"] = self.sqlite.json_loads(data.pop("metadata_json", "{}"))
        return data

    def _note_from_row(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        data["metadata"] = self.sqlite.json_loads(data.pop("metadata_json", "{}"))
        return data


def _slug(value: Any) -> str:
    text = str(value or "").strip().casefold().replace(" ", "-")
    text = _SLUG_RE.sub("-", text).strip("-_")
    return text[:80] or gen_id("memo-folder-")


def _title_from_content(content: str) -> str:
    first = str(content or "").strip().splitlines()[0] if str(content or "").strip() else "Untitled memo"
    return first[:80] or "Untitled memo"


def _score(query: str, content: str) -> float:
    q = str(query or "").lower().strip()
    c = str(content or "").lower().strip()
    if not q:
        return 0.1
    if q in c:
        return round(len(q) / max(len(c), 1), 4)
    q_words = set(q.split())
    if not q_words:
        return 0.0
    c_words = set(c.split())
    return round(len(q_words & c_words) / len(q_words), 4)
