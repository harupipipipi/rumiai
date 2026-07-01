"""Prompt Manager — テンプレートベースのプロンプト管理。

機能:
    - インメモリ dict + JSON ファイル永続化
    - PromptTemplate ベースの管理
    - コンテキスト変数の自動注入
    - 後方互換: 旧 create_prompt / get_prompt API はそのまま動作する

永続化先: user_data/shared/prompts/{name}.json

データ形式:
    {
        "id":          str,
        "name":        str,
        "content":     str,          # body のエイリアス（後方互換）
        "body":        str,          # テンプレート本文
        "description": str,
        "variables":   [{"name": str, "type": str, "default": Any, "required": bool}],
        "metadata":    dict,
        "created_at":  str,          # ISO 8601
        "updated_at":  str           # ISO 8601
    }
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

from ..extensions.runtime import get_extension_registry, get_extensions_root
from .component_prompts import component_prompt_records
from .template import PromptTemplate
from .trust import prompt_pack_is_trusted, prompt_pack_source_is_trusted


# ---------------------------------------------------------------------------
# 永続化ディレクトリ
# ---------------------------------------------------------------------------
_PROMPTS_DIR: str | None = None
_PROMPT_ID_SAFE_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _get_prompts_dir() -> str:
    """user_data/shared/prompts/ の絶対パスを返す。なければ作成する。

    基準: このファイルの実体パス（シンボリックリンク解決済み）から
    ../../user_data/shared/prompts を辿り、Pack ルート内に配置する。
    """
    global _PROMPTS_DIR
    if _PROMPTS_DIR is not None:
        return _PROMPTS_DIR

    # realpath でシンボリックリンクを解決し、Pack ルートを正確に特定する
    base = os.path.dirname(os.path.realpath(__file__))
    prompts_dir = os.path.normpath(
        os.path.join(base, "..", "..", "user_data", "shared", "prompts")
    )
    os.makedirs(prompts_dir, exist_ok=True)
    _PROMPTS_DIR = prompts_dir
    return _PROMPTS_DIR


def _safe_filename(name: str) -> str:
    """name をファイル名に安全な形式に変換する。"""
    safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in name)
    return safe or "unnamed"


def _read_pack_id(pack_root: Path) -> str:
    try:
        raw = json.loads((pack_root / "ecosystem.json").read_text(encoding="utf-8"))
        pack_id = str(raw.get("pack_id") or "").strip()
        if pack_id:
            return pack_id
    except Exception:
        pass
    return pack_root.name


# ---------------------------------------------------------------------------
# PromptManager
# ---------------------------------------------------------------------------
class PromptManager:
    """プロンプトをインメモリ dict + JSON ファイルで管理する。"""

    def __init__(self):
        self._prompts: dict[str, dict] = {}
        self._name_index: dict[str, str] = {}  # name → id
        self._system_prompt: str = ""
        self._loaded = False

    # -- 永続化 ---------------------------------------------------------------
    def _ensure_loaded(self) -> None:
        """初回アクセス時に JSON ファイルからロードする。"""
        if self._loaded:
            return
        self._loaded = True
        prompts_dir = _get_prompts_dir()
        if not os.path.isdir(prompts_dir):
            return
        for fname in os.listdir(prompts_dir):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(prompts_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                pid = data.get("id", "")
                if pid:
                    self._prompts[pid] = data
                    name = data.get("name", "")
                    if name:
                        self._name_index[name] = pid
            except (json.JSONDecodeError, OSError):
                continue

    def _save_prompt(self, prompt: dict) -> None:
        """プロンプトを JSON ファイルに保存する。"""
        fpath = self.prompt_path_for_name(str(prompt.get("name") or "unnamed"))
        tmp_path = fpath.with_suffix(fpath.suffix + f".tmp.{os.getpid()}.{uuid.uuid4().hex}")
        tmp_path.write_text(
            json.dumps(prompt, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        tmp_path.replace(fpath)

    def prompt_path_for_name(self, name: str) -> Path:
        """Return the durable JSON path for a user-owned prompt name."""
        prompts_dir = Path(_get_prompts_dir())
        prompts_dir.mkdir(parents=True, exist_ok=True)
        return prompts_dir / (_safe_filename(name) + ".json")

    def _delete_prompt_file(self, name: str) -> None:
        """プロンプトの JSON ファイルを削除する。"""
        prompts_dir = _get_prompts_dir()
        fname = _safe_filename(name) + ".json"
        fpath = os.path.join(prompts_dir, fname)
        if os.path.isfile(fpath):
            os.remove(fpath)

    def _canonical_prompt_path(self, prompt_id: str) -> Path | None:
        """Locate the canonical in-pack prompt file for a given prompt_id.

        Used as a fallback when an extension override does not ship a body, so
        we don't have to keep a duplicate prompt.md in extensions/prompts/<id>/.
        """
        if not prompt_id or not _PROMPT_ID_SAFE_RE.match(prompt_id):
            return None
        base = Path(os.path.dirname(os.path.realpath(__file__)))
        candidates = [
            base.parent / "prompts" / prompt_id / "prompt.md",
            base.parent / "prompts" / (prompt_id + ".system.md"),
        ]
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        return None

    def _extension_prompts(self) -> dict[str, dict]:
        prompts: dict[str, dict] = {}
        try:
            registry = get_extension_registry()
            extensions_root = get_extensions_root()
            for manifest in registry.prompts().list(enabled_only=True):
                prompt_id = str(manifest.get("id", "")).strip()
                if not prompt_id:
                    continue
                source_pack_id = str(
                    manifest.get("source_pack_id")
                    or manifest.get("_source_pack_id")
                    or extensions_root.parent.name
                ).strip()
                if not prompt_pack_source_is_trusted(source_pack_id, manifest.get("source_path", "")):
                    continue
                template_file = str(
                    (manifest.get("config", {}) or {}).get("template_file", "prompt.md")
                ).strip() or "prompt.md"
                prompt_path = extensions_root / "prompts" / prompt_id / template_file
                body = ""
                source = "extension"
                if prompt_path.is_file():
                    body = prompt_path.read_text(encoding="utf-8").strip()
                if not body:
                    canonical = self._canonical_prompt_path(prompt_id)
                    if canonical is not None:
                        body = canonical.read_text(encoding="utf-8").strip()
                        source = "canonical_fallback"
                prompts[prompt_id] = {
                    "id": prompt_id,
                    "name": prompt_id,
                    "content": body,
                    "body": body,
                    "description": str(manifest.get("description", "")),
                    "variables": list((manifest.get("config", {}) or {}).get("variables", [])),
                    "metadata": {
                        "source": source,
                        "source_pack_id": source_pack_id,
                        "manifest_path": manifest.get("source_path", ""),
                    },
                    "created_at": "",
                    "updated_at": "",
                    "read_only": True,
                    "source_pack_id": source_pack_id,
                }
        except Exception:
            return {}
        return prompts

    def _pack_prompts(self) -> dict[str, dict]:
        prompts: dict[str, dict] = {}
        ecosystem_root = Path(__file__).resolve().parents[3]
        if not ecosystem_root.exists():
            return prompts
        for pack_root in sorted(ecosystem_root.iterdir()):
            if not pack_root.is_dir() or not (pack_root / "ecosystem.json").exists():
                continue
            prompt_dir = pack_root / "prompts"
            if not prompt_dir.exists():
                continue
            source_pack_id = _read_pack_id(pack_root)
            if not prompt_pack_is_trusted(source_pack_id):
                continue
            for prompt_path in sorted(prompt_dir.glob("*.system.md")):
                try:
                    body = prompt_path.read_text(encoding="utf-8")
                except OSError:
                    continue
                prompt_id = prompt_path.name.removesuffix(".system.md")
                prompts[prompt_id] = {
                    "id": prompt_id,
                    "name": prompt_id,
                    "content": body,
                    "body": body,
                    "description": "",
                    "variables": [],
                    "metadata": {
                        "source": "pack",
                        "source_pack_id": source_pack_id,
                        "path": str(prompt_path),
                    },
                    "created_at": "",
                    "updated_at": "",
                    "read_only": True,
                    "source_pack_id": source_pack_id,
                }
        return prompts

    def _component_prompts(self) -> dict[str, dict]:
        return component_prompt_records()

    # -- 一覧 ---------------------------------------------------------------
    def list_prompts(self) -> list[dict]:
        """保存されたプロンプト一覧を返す。"""
        self._ensure_loaded()
        combined = dict(self._pack_prompts())
        combined.update(self._component_prompts())
        combined.update(self._extension_prompts())
        combined.update(self._prompts)
        return list(combined.values())

    # -- 取得 ---------------------------------------------------------------
    def get_prompt(self, prompt_id: str) -> dict | None:
        """ID でプロンプトを取得する。存在しなければ None。"""
        self._ensure_loaded()
        prompt = self._prompts.get(prompt_id)
        if prompt is not None:
            return prompt
        return (
            self._extension_prompts().get(prompt_id)
            or self._component_prompts().get(prompt_id)
            or self._pack_prompts().get(prompt_id)
        )

    def get_prompt_by_name(self, name: str) -> dict | None:
        """name でプロンプトを取得する。存在しなければ None。"""
        self._ensure_loaded()
        pid = self._name_index.get(name)
        if pid is not None:
            return self._prompts.get(pid)
        return (
            self._extension_prompts().get(name)
            or self._component_prompts().get(name)
            or self._pack_prompts().get(name)
        )

    # -- 作成 ---------------------------------------------------------------
    def create_prompt(self, data: dict) -> dict:
        """新規プロンプトを作成して返す。

        Args:
            data: {"name": str, "content": str, "variables": [...], ...}
                  content は body のエイリアスとして扱う。
                  新形式の "body", "description", "metadata" も受け付ける。
        Returns:
            作成されたプロンプト dict
        """
        self._ensure_loaded()
        prompt_id = uuid.uuid4().hex[:8]
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        name = data.get("name", "")
        body = data.get("body", data.get("content", ""))
        description = data.get("description", "")
        metadata = data.get("metadata", {})

        # variables: 旧形式 [str, ...] と新形式 [{"name":...}, ...] の両方を受け付ける
        raw_vars = data.get("variables", [])
        variables = _normalize_variables(raw_vars)

        prompt = {
            "id": prompt_id,
            "name": name,
            "content": body,
            "body": body,
            "description": description,
            "variables": variables,
            "metadata": metadata,
            "created_at": now,
            "updated_at": now,
        }
        self._prompts[prompt_id] = prompt
        if name:
            self._name_index[name] = prompt_id
        self._save_prompt(prompt)
        return prompt

    # -- 更新 ---------------------------------------------------------------
    def update_prompt(self, name: str, updates: dict) -> dict | None:
        """既存プロンプトを更新する。

        Args:
            name:    プロンプト名
            updates: 更新するフィールド dict
        Returns:
            更新後のプロンプト dict。見つからなければ None。
        """
        self._ensure_loaded()
        pid = self._name_index.get(name)
        if pid is None:
            return None
        prompt = self._prompts.get(pid)
        if prompt is None:
            return None

        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        old_name = prompt.get("name", "")

        for key in ("description", "metadata"):
            if key in updates:
                prompt[key] = updates[key]

        if "content" in updates or "body" in updates:
            new_body = updates.get("body", updates.get("content", prompt["body"]))
            prompt["body"] = new_body
            prompt["content"] = new_body

        if "variables" in updates:
            prompt["variables"] = _normalize_variables(updates["variables"])

        if "name" in updates and updates["name"] != old_name:
            # 名前変更: インデックスと古いファイルを更新
            self._delete_prompt_file(old_name)
            del self._name_index[old_name]
            prompt["name"] = updates["name"]
            self._name_index[updates["name"]] = pid

        prompt["updated_at"] = now
        self._save_prompt(prompt)
        return prompt

    # -- 削除 ---------------------------------------------------------------
    def delete_prompt(self, name: str) -> bool:
        """プロンプトを削除する。成功時 True、見つからなければ False。"""
        self._ensure_loaded()
        pid = self._name_index.get(name)
        if pid is None:
            return False
        prompt = self._prompts.get(pid)
        if prompt is None:
            return False
        self._delete_prompt_file(name)
        del self._prompts[pid]
        del self._name_index[name]
        return True

    # -- テンプレート変換 -----------------------------------------------------
    def to_template(self, name: str) -> PromptTemplate | None:
        """保存済みプロンプトを PromptTemplate に変換する。"""
        prompt = self.get_prompt_by_name(name)
        if prompt is None:
            return None
        return PromptTemplate(
            name=prompt.get("name", ""),
            description=prompt.get("description", ""),
            variables=prompt.get("variables", []),
            body=prompt.get("body", prompt.get("content", "")),
            metadata=prompt.get("metadata", {}),
        )

    def create_from_template(self, template: PromptTemplate) -> dict:
        """PromptTemplate からプロンプトを作成する。"""
        return self.create_prompt(template.to_dict())

    # -- コンテキスト変数注入 ---------------------------------------------------
    @staticmethod
    def inject_context_variables(
        variables: dict,
        context: dict | None = None,
    ) -> dict:
        """context dict から特殊変数を variables に注入する。

        注入されるキー:
            context.total_tokens    — context["total_tokens"] (int, default 0)
            context.message_count   — context["message_count"] (int, default 0)
            context.messages        — context["messages"] (str / list, default "")
            context.system_prompt   — context["system_prompt"] (str, default "")
            context.conversation_id — context["conversation_id"] (str, default "")
            context.knowledge       — context["knowledge"] (str, default "")
            context.memory          — context["memory"] (str, default "")

        既にユーザーが明示的に指定した値は上書きしない。
        """
        if context is None:
            return variables

        ctx_mapping = {
            "context.total_tokens": "total_tokens",
            "context.message_count": "message_count",
            "context.messages": "messages",
            "context.system_prompt": "system_prompt",
            "context.conversation_id": "conversation_id",
            "context.knowledge": "knowledge",
            "context.memory": "memory",
        }
        merged = dict(variables)
        for template_key, ctx_key in ctx_mapping.items():
            if template_key not in merged and ctx_key in context:
                value = context[ctx_key]
                if isinstance(value, (list, dict)):
                    value = json.dumps(value, ensure_ascii=False)
                merged[template_key] = value
        return merged

    # -- システムプロンプト ---------------------------------------------------
    def get_system_prompt(self) -> str:
        """システムプロンプトを取得する。"""
        return self._system_prompt

    def set_system_prompt(self, content: str) -> str:
        """システムプロンプトを設定して返す。"""
        self._system_prompt = str(content)
        return self._system_prompt


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------
def _normalize_variables(raw: list) -> list[dict]:
    """変数リストを正規化する。

    旧形式 ["var1", "var2"] → [{"name": "var1", ...}, ...]
    新形式 [{"name": "var1", "type": "string", ...}] → そのまま
    """
    if not raw:
        return []
    normalized = []
    for item in raw:
        if isinstance(item, str):
            normalized.append({
                "name": item,
                "type": "string",
                "default": None,
                "required": False,
            })
        elif isinstance(item, dict):
            normalized.append({
                "name": item.get("name", ""),
                "type": item.get("type", "string"),
                "default": item.get("default"),
                "required": item.get("required", False),
            })
        # 不明な型は無視
    return normalized


# ---------------------------------------------------------------------------
# モジュールレベル シングルトン
# ---------------------------------------------------------------------------
_manager = PromptManager()


def get_manager() -> PromptManager:
    """共有 PromptManager インスタンスを返す。"""
    return _manager
