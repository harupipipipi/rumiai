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


def _slugify_prompt_id(value: str, fallback: str = "system_prompt") -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", str(value or "").strip()).strip("_-").lower()
    return slug or fallback


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _prompt_text(prompt: dict | None) -> str:
    if not isinstance(prompt, dict):
        return ""
    return str(prompt.get("body") or prompt.get("content") or "")


def _get_shared_dir() -> Path:
    prompts_dir = Path(_get_prompts_dir())
    return prompts_dir.parent if prompts_dir.name == "prompts" else prompts_dir


def _get_system_prompt_state_path() -> Path:
    return _get_shared_dir() / "system_prompt_state.json"


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
        prompts_dir = _get_prompts_dir()
        os.makedirs(prompts_dir, exist_ok=True)
        name = prompt.get("name", "unnamed")
        fname = _safe_filename(name) + ".json"
        fpath = os.path.join(prompts_dir, fname)
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(prompt, f, ensure_ascii=False, indent=2)

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
            registry = get_extension_registry(force_reload=True)
            extensions_root = get_extensions_root()
            for manifest in registry.prompts().list(enabled_only=True):
                prompt_id = str(manifest.get("id", "")).strip()
                if not prompt_id:
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
                        "manifest_path": manifest.get("source_path", ""),
                    },
                    "created_at": "",
                    "updated_at": "",
                    "read_only": True,
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

    # -- System prompt profiles --------------------------------------------
    def _read_system_prompt_state(self) -> dict:
        path = _get_system_prompt_state_path()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write_system_prompt_state(self, state: dict) -> None:
        path = _get_system_prompt_state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def _system_prompt_record(self, prompt: dict, active_id: str = "") -> dict:
        metadata = prompt.get("metadata") if isinstance(prompt.get("metadata"), dict) else {}
        prompt_id = str(prompt.get("id") or prompt.get("name") or "")
        name = str(prompt.get("name") or prompt_id)
        body = _prompt_text(prompt)
        tags = prompt.get("tags", metadata.get("tags", []))
        if not isinstance(tags, list):
            tags = []
        variables = prompt.get("variables", [])
        if not isinstance(variables, list):
            variables = []
        source = str(metadata.get("source") or ("user" if prompt_id in self._prompts else "prompt"))
        is_active = bool(active_id and (active_id == prompt_id or active_id == name))
        return {
            "id": prompt_id,
            "name": name,
            "description": str(prompt.get("description") or ""),
            "body": body,
            "content": body,
            "tags": [str(tag) for tag in tags],
            "variables": variables,
            "metadata": metadata,
            "source": source,
            "source_pack_id": str(prompt.get("source_pack_id") or metadata.get("source_pack_id") or ""),
            "read_only": bool(prompt.get("read_only")) or prompt_id not in self._prompts,
            "active": is_active,
            "created_at": str(prompt.get("created_at") or ""),
            "updated_at": str(prompt.get("updated_at") or ""),
            "char_count": len(body),
            "token_estimate": max(0, int(round(len(body) / 4))),
            "variable_count": len(variables),
        }

    def _mutable_prompt_id(self, prompt_id_or_name: str) -> str | None:
        self._ensure_loaded()
        key = str(prompt_id_or_name or "").strip()
        if not key:
            return None
        if key in self._prompts:
            return key
        pid = self._name_index.get(key)
        if pid in self._prompts:
            return pid
        return None

    def _unique_system_prompt_id(self, requested_id: str, name: str) -> str:
        base = _slugify_prompt_id(requested_id or name)
        if not base.startswith("system_"):
            base = "system_" + base
        existing_ids = {str(prompt.get("id") or "") for prompt in self.list_prompts()}
        if base not in existing_ids:
            return base
        index = 2
        while f"{base}_{index}" in existing_ids:
            index += 1
        return f"{base}_{index}"

    def list_system_prompts(self) -> dict:
        state = self._read_system_prompt_state()
        active_id = str(state.get("active_id") or "").strip()
        active_content = self.get_system_prompt()
        records = []
        seen: set[str] = set()
        for prompt in self.list_prompts():
            prompt_id = str(prompt.get("id") or prompt.get("name") or "")
            if not prompt_id or prompt_id in seen:
                continue
            seen.add(prompt_id)
            records.append(self._system_prompt_record(prompt, active_id))
        records.sort(key=lambda item: (
            not bool(item.get("active")),
            bool(item.get("read_only")),
            str(item.get("name") or item.get("id") or "").lower(),
        ))
        return {
            "prompts": records,
            "active_id": active_id,
            "active_content": active_content,
            "inline_content": str(state.get("content") or ""),
        }

    def create_system_prompt(self, data: dict) -> dict:
        self._ensure_loaded()
        name = str(data.get("name") or "").strip() or "System Prompt"
        body = str(data.get("body", data.get("content", "")))
        requested_id = str(data.get("id") or data.get("prompt_id") or "").strip()
        prompt_id = self._unique_system_prompt_id(requested_id, name)
        existing_names = {str(prompt.get("name") or "") for prompt in self.list_prompts()}
        if name in existing_names:
            suffix = 2
            base_name = name
            while f"{base_name} {suffix}" in existing_names:
                suffix += 1
            name = f"{base_name} {suffix}"
        metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
        metadata = {
            **metadata,
            "kind": "system_prompt",
            "source": metadata.get("source") or "user",
        }
        tags = data.get("tags", metadata.get("tags", []))
        if not isinstance(tags, list):
            tags = []
        now = _now_iso()
        prompt = {
            "id": prompt_id,
            "name": name,
            "content": body,
            "body": body,
            "description": str(data.get("description") or ""),
            "variables": _normalize_variables(data.get("variables", [])),
            "metadata": metadata,
            "tags": [str(tag) for tag in tags if str(tag).strip()],
            "created_at": now,
            "updated_at": now,
        }
        self._prompts[prompt_id] = prompt
        self._name_index[name] = prompt_id
        self._save_prompt(prompt)
        if data.get("activate"):
            self.activate_system_prompt(prompt_id)
        return self._system_prompt_record(prompt, prompt_id if data.get("activate") else "")

    def update_system_prompt(self, prompt_id_or_name: str, updates: dict) -> dict | None:
        pid = self._mutable_prompt_id(prompt_id_or_name)
        if pid is None:
            return None
        prompt = self._prompts[pid]
        old_name = str(prompt.get("name") or "")
        now = _now_iso()

        if "description" in updates:
            prompt["description"] = str(updates.get("description") or "")
        if "metadata" in updates and isinstance(updates.get("metadata"), dict):
            metadata = dict(updates["metadata"])
            metadata.setdefault("kind", "system_prompt")
            metadata.setdefault("source", "user")
            prompt["metadata"] = metadata
        elif isinstance(prompt.get("metadata"), dict):
            prompt["metadata"] = {**prompt["metadata"], "kind": "system_prompt"}
        if "tags" in updates:
            tags = updates.get("tags")
            prompt["tags"] = [str(tag) for tag in tags] if isinstance(tags, list) else []
        if "variables" in updates:
            prompt["variables"] = _normalize_variables(updates["variables"])
        if "content" in updates or "body" in updates:
            new_body = str(updates.get("body", updates.get("content", prompt.get("body", ""))))
            prompt["body"] = new_body
            prompt["content"] = new_body
        if "name" in updates:
            new_name = str(updates.get("name") or "").strip()
            if new_name and new_name != old_name:
                if new_name in self._name_index and self._name_index[new_name] != pid:
                    return None
                self._delete_prompt_file(old_name)
                self._name_index.pop(old_name, None)
                prompt["name"] = new_name
                self._name_index[new_name] = pid

        prompt["updated_at"] = now
        self._save_prompt(prompt)
        active_id = str(self._read_system_prompt_state().get("active_id") or "")
        if active_id in (pid, old_name, str(prompt.get("name") or "")):
            self.activate_system_prompt(pid)
            active_id = pid
        return self._system_prompt_record(prompt, active_id)

    def delete_system_prompt(self, prompt_id_or_name: str) -> bool:
        pid = self._mutable_prompt_id(prompt_id_or_name)
        if pid is None:
            return False
        prompt = self._prompts.get(pid)
        if prompt is None:
            return False
        name = str(prompt.get("name") or "")
        self._delete_prompt_file(name)
        self._prompts.pop(pid, None)
        self._name_index.pop(name, None)
        state = self._read_system_prompt_state()
        active_id = str(state.get("active_id") or "")
        if active_id in (pid, name):
            self._system_prompt = ""
            self._write_system_prompt_state({
                "active_id": "",
                "content": "",
                "updated_at": _now_iso(),
            })
        return True

    def activate_system_prompt(self, prompt_id_or_name: str) -> dict | None:
        key = str(prompt_id_or_name or "").strip()
        prompt = self.get_prompt(key) or self.get_prompt_by_name(key)
        if prompt is None:
            return None
        prompt_id = str(prompt.get("id") or prompt.get("name") or key)
        content = _prompt_text(prompt)
        self._system_prompt = content
        self._write_system_prompt_state({
            "active_id": prompt_id,
            "content": content,
            "updated_at": _now_iso(),
        })
        return {
            "active_id": prompt_id,
            "content": content,
            "prompt": self._system_prompt_record(prompt, prompt_id),
        }

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
        state = self._read_system_prompt_state()
        active_id = str(state.get("active_id") or "").strip()
        if active_id:
            prompt = self.get_prompt(active_id) or self.get_prompt_by_name(active_id)
            content = _prompt_text(prompt)
            if content:
                self._system_prompt = content
                return self._system_prompt
        content = str(state.get("content") or "")
        if content:
            self._system_prompt = content
            return self._system_prompt
        return self._system_prompt

    def set_system_prompt(self, content: str) -> str:
        """システムプロンプトを設定して返す。"""
        self._system_prompt = str(content)
        self._write_system_prompt_state({
            "active_id": "",
            "content": self._system_prompt,
            "updated_at": _now_iso(),
        })
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
