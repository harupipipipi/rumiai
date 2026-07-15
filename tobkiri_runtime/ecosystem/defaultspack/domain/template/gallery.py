"""domain.template.gallery — テンプレートギャラリー管理。

インメモリ dict + JSON ファイル永続化でテンプレートを管理する。
永続化先: user_data/shared/templates/{safe_name}.template.json

ギャラリーは UnifiedTemplate を保存・検索・エクスポート・インポートするための
コレクションとして機能する。
"""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any

from domain.template.unified import UnifiedTemplate


# ---------------------------------------------------------------------------
# 永続化ディレクトリ
# ---------------------------------------------------------------------------
_TEMPLATES_DIR: str | None = None


def _get_templates_dir() -> str:
    """user_data/shared/templates/ の絶対パスを返す。なければ作成する。"""
    global _TEMPLATES_DIR
    if _TEMPLATES_DIR is not None:
        return _TEMPLATES_DIR

    base = os.path.dirname(os.path.realpath(__file__))
    templates_dir = os.path.normpath(
        os.path.join(base, "..", "..", "user_data", "shared", "templates")
    )
    os.makedirs(templates_dir, exist_ok=True)
    _TEMPLATES_DIR = templates_dir
    return _TEMPLATES_DIR


def _safe_filename(name: str) -> str:
    """name をファイル名に安全な形式に変換する。"""
    safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in name)
    return safe or "unnamed"


def _now_iso() -> str:
    """ISO 8601 タイムスタンプを返す。"""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------------------------------------------------------------------------
# GalleryEntry — ギャラリーエントリ
# ---------------------------------------------------------------------------

class GalleryEntry:
    """ギャラリー内の1つのテンプレートエントリ。

    UnifiedTemplate + ギャラリー固有メタデータを保持する。

    Attributes:
        entry_id:    一意 ID
        template:    UnifiedTemplate インスタンス
        tags:        検索用タグ
        author:      作成者
        created_at:  作成日時 (ISO 8601)
        updated_at:  更新日時 (ISO 8601)
    """

    __slots__ = ("entry_id", "template", "tags", "author", "created_at", "updated_at")

    def __init__(
        self,
        entry_id: str = "",
        template: UnifiedTemplate | None = None,
        tags: list[str] | None = None,
        author: str = "",
        created_at: str = "",
        updated_at: str = "",
    ):
        self.entry_id = entry_id or uuid.uuid4().hex[:12]
        self.template = template or UnifiedTemplate()
        self.tags = list(tags or [])
        self.author = author
        self.created_at = created_at or _now_iso()
        self.updated_at = updated_at or self.created_at

    def to_dict(self) -> dict:
        """シリアライズ用 dict を返す。"""
        return {
            "entry_id": self.entry_id,
            "template": self.template.to_dict(),
            "tags": list(self.tags),
            "author": self.author,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GalleryEntry":
        """dict から復元する。"""
        template_data = data.get("template", {})
        return cls(
            entry_id=data.get("entry_id", ""),
            template=UnifiedTemplate.from_dict(template_data),
            tags=data.get("tags"),
            author=data.get("author", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )

    def to_summary(self) -> dict:
        """一覧表示用の要約 dict を返す。"""
        return {
            "entry_id": self.entry_id,
            "name": self.template.name,
            "description": self.template.description,
            "source_type": self.template.source_type,
            "tags": list(self.tags),
            "author": self.author,
            "parameter_count": len(self.template.parameters.get("properties", {})),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


# ---------------------------------------------------------------------------
# TemplateGallery — ギャラリー管理
# ---------------------------------------------------------------------------

class TemplateGallery:
    """テンプレートギャラリーの管理クラス。

    インメモリ dict と user_data/shared/templates/ へのファイル永続化を行う。
    """

    def __init__(self):
        self._entries: dict[str, GalleryEntry] = {}
        self._name_index: dict[str, str] = {}  # name → entry_id
        self._loaded = False

    # -- 永続化 ---------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        """初回アクセス時にファイルからロードする。"""
        if self._loaded:
            return
        self._loaded = True
        templates_dir = _get_templates_dir()
        if not os.path.isdir(templates_dir):
            return
        for fname in os.listdir(templates_dir):
            if not fname.endswith(".template.json"):
                continue
            fpath = os.path.join(templates_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                entry = GalleryEntry.from_dict(data)
                self._entries[entry.entry_id] = entry
                if entry.template.name:
                    self._name_index[entry.template.name] = entry.entry_id
            except (json.JSONDecodeError, OSError, KeyError):
                continue

    def _save_entry(self, entry: GalleryEntry) -> None:
        """エントリをファイルに保存する。"""
        templates_dir = _get_templates_dir()
        fname = _safe_filename(entry.template.name) + ".template.json"
        fpath = os.path.join(templates_dir, fname)
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(entry.to_dict(), f, ensure_ascii=False, indent=2)

    def _delete_entry_file(self, name: str) -> None:
        """エントリのファイルを削除する。"""
        templates_dir = _get_templates_dir()
        fname = _safe_filename(name) + ".template.json"
        fpath = os.path.join(templates_dir, fname)
        if os.path.isfile(fpath):
            os.remove(fpath)

    # -- 一覧 ---------------------------------------------------------------

    def list_entries(
        self,
        source_type: str | None = None,
        tag: str | None = None,
        query: str | None = None,
    ) -> list[dict]:
        """ギャラリーエントリの要約一覧を返す。

        Args:
            source_type: "tool", "prompt", "unified" でフィルタ
            tag:         タグでフィルタ
            query:       名前・説明のテキスト検索
        """
        self._ensure_loaded()
        results: list[dict] = []

        for entry in self._entries.values():
            if source_type and entry.template.source_type != source_type:
                continue
            if tag and tag not in entry.tags:
                continue
            if query:
                q_lower = query.lower()
                name_match = q_lower in entry.template.name.lower()
                desc_match = q_lower in entry.template.description.lower()
                tag_match = any(q_lower in t.lower() for t in entry.tags)
                if not (name_match or desc_match or tag_match):
                    continue
            results.append(entry.to_summary())

        results.sort(key=lambda e: e.get("updated_at", ""), reverse=True)
        return results

    # -- 取得 ---------------------------------------------------------------

    def get_entry(self, entry_id: str) -> GalleryEntry | None:
        """ID でエントリを取得する。"""
        self._ensure_loaded()
        return self._entries.get(entry_id)

    def get_entry_by_name(self, name: str) -> GalleryEntry | None:
        """名前でエントリを取得する。"""
        self._ensure_loaded()
        eid = self._name_index.get(name)
        if eid is None:
            return None
        return self._entries.get(eid)

    # -- 追加 ---------------------------------------------------------------

    def add_entry(
        self,
        template: UnifiedTemplate,
        tags: list[str] | None = None,
        author: str = "",
    ) -> GalleryEntry:
        """テンプレートをギャラリーに追加する。

        同名のエントリが存在する場合は上書き更新する。
        """
        self._ensure_loaded()
        existing_eid = self._name_index.get(template.name)

        if existing_eid and existing_eid in self._entries:
            entry = self._entries[existing_eid]
            entry.template = template
            entry.tags = list(tags) if tags is not None else entry.tags
            if author:
                entry.author = author
            entry.updated_at = _now_iso()
        else:
            entry = GalleryEntry(
                template=template,
                tags=tags,
                author=author,
            )

        self._entries[entry.entry_id] = entry
        if template.name:
            self._name_index[template.name] = entry.entry_id
        self._save_entry(entry)
        return entry

    # -- 削除 ---------------------------------------------------------------

    def remove_entry(self, entry_id: str) -> bool:
        """エントリを削除する。成功時 True。"""
        self._ensure_loaded()
        entry = self._entries.get(entry_id)
        if entry is None:
            return False
        name = entry.template.name
        self._delete_entry_file(name)
        del self._entries[entry_id]
        if name and self._name_index.get(name) == entry_id:
            del self._name_index[name]
        return True

    # -- エクスポート / インポート -----------------------------------------------

    def export_entry(self, entry_id: str) -> dict | None:
        """エントリをエクスポート用 dict として返す。

        JSON 共有形式で、他の環境にインポートできる。
        """
        self._ensure_loaded()
        entry = self._entries.get(entry_id)
        if entry is None:
            return None
        export_data = entry.to_dict()
        export_data["_export_version"] = "1.0"
        export_data["_exported_at"] = _now_iso()
        return export_data

    def import_entry(
        self,
        data: dict,
        author: str = "",
        overwrite: bool = False,
    ) -> GalleryEntry:
        """エクスポートされた dict からエントリをインポートする。

        Args:
            data:      エクスポート形式の dict (to_dict() の戻り値)
            author:    インポート時の作成者 (空なら元の author を使う)
            overwrite: 同名エントリが存在する場合に上書きするか

        Returns:
            インポートされた GalleryEntry

        Raises:
            ValueError: overwrite=False で同名エントリが存在する場合
        """
        self._ensure_loaded()

        template_data = data.get("template", data)
        # エクスポート形式の場合は template キー配下にテンプレートがある
        # 直接 UnifiedTemplate 形式の場合もある
        if "template" in data and isinstance(data["template"], dict):
            template_data = data["template"]

        template = UnifiedTemplate.from_dict(template_data)

        # 同名チェック
        existing_eid = self._name_index.get(template.name)
        if existing_eid and not overwrite:
            raise ValueError(
                f"Template '{template.name}' already exists. Use overwrite=True to replace."
            )

        import_tags = data.get("tags", [])
        import_author = author or data.get("author", "")

        entry = self.add_entry(
            template=template,
            tags=import_tags,
            author=import_author,
        )
        return entry


# ---------------------------------------------------------------------------
# モジュールレベル シングルトン
# ---------------------------------------------------------------------------
_gallery: TemplateGallery | None = None


def get_gallery() -> TemplateGallery:
    """共有 TemplateGallery インスタンスを返す。"""
    global _gallery
    if _gallery is None:
        _gallery = TemplateGallery()
    return _gallery
