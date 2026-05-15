import json
import os
import threading
from pathlib import Path

from ..extensions.runtime import get_extension_registry


class ToolRegistry:
    """ツール定義の登録・管理（シングルトン・インメモリ + 永続化）"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._tools = {}
        self._mcp_servers = {}
        self._lock = threading.Lock()
        self._tools_dir = self._resolve_tools_dir()
        self._load_pack_tools()
        self._load_dynamic_tools()

    # ------------------------------------------------------------------
    # tools directory resolution
    # ------------------------------------------------------------------

    def _resolve_tools_dir(self):
        """user_data/shared/tools/ ディレクトリのパスを解決し、なければ作成する"""
        base = os.path.dirname(os.path.abspath(__file__))
        # domain/tool/ -> pack root -> user_data/shared/tools/
        pack_root = os.path.normpath(os.path.join(base, "..", ".."))
        tools_dir = os.path.join(pack_root, "user_data", "shared", "tools")
        os.makedirs(tools_dir, exist_ok=True)
        return tools_dir

    # ------------------------------------------------------------------
    # pack-provided tools
    # ------------------------------------------------------------------

    def _pack_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    def _ecosystem_dir(self) -> Path:
        return self._pack_root().parent

    def _installed_pack_roots(self) -> list[Path]:
        ecosystem_dir = self._ecosystem_dir()
        if not ecosystem_dir.is_dir():
            return [self._pack_root()]
        roots: list[Path] = []
        for path in sorted(ecosystem_dir.iterdir()):
            if path.is_dir() and (path / "ecosystem.json").is_file():
                roots.append(path)
        return roots

    def _load_pack_tools(self):
        loaded = self._load_extension_tools()
        for pack_root in self._installed_pack_roots():
            loaded += self._load_tools_from_pack(pack_root)
        self._apply_extension_skill_metadata()
        return loaded

    def _load_tools_from_pack(self, pack_root: Path) -> int:
        loaded = 0
        for manifest_path in sorted((pack_root / "tools").glob("*/manifest.json")):
            tool_def = self._tool_from_path_manifest(manifest_path, pack_root)
            if tool_def is not None:
                self.register(tool_def)
                loaded += 1
        for manifest_path in sorted((pack_root / "tools").glob("*/tool.json")):
            tool_def = self._tool_from_path_manifest(manifest_path, pack_root)
            if tool_def is not None:
                self.register(tool_def)
                loaded += 1
        for manifest_path in sorted((pack_root / "extensions" / "tools").glob("*/manifest.json")):
            tool_def = self._tool_from_path_manifest(manifest_path, pack_root)
            if tool_def is not None:
                self.register(tool_def)
                loaded += 1
        return loaded

    def _tool_from_path_manifest(self, manifest_path: Path, pack_root: Path):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(manifest, dict):
            return None
        manifest["source_path"] = str(manifest_path)
        tool_def = self._tool_from_manifest(manifest)
        if tool_def is None:
            return None
        pack_id = self._pack_id_from_root(pack_root)
        metadata = dict(tool_def.get("metadata", {}))
        metadata["source_pack_id"] = pack_id
        metadata["source"] = "pack"
        tool_def["metadata"] = metadata
        tool_def["source_pack_id"] = pack_id
        return tool_def

    @staticmethod
    def _pack_id_from_root(pack_root: Path) -> str:
        try:
            raw = json.loads((pack_root / "ecosystem.json").read_text(encoding="utf-8"))
            pack_id = str(raw.get("pack_id") or "").strip()
            if pack_id:
                return pack_id
        except Exception:
            pass
        return pack_root.name

    def _load_extension_tools(self):
        """extension manifests から built-in tools を構築する。"""
        loaded = 0
        try:
            manifests = get_extension_registry(force_reload=True).tools().list(
                enabled_only=True
            )
        except Exception:
            return 0

        for manifest in manifests:
            tool_def = self._tool_from_manifest(manifest)
            if tool_def is None:
                continue
            self.register(tool_def)
            loaded += 1
        return loaded

    def _apply_extension_skill_metadata(self):
        """skill manifests can annotate tools without becoming executable tools."""
        try:
            skills = get_extension_registry(force_reload=True).skills().list(
                enabled_only=True
            )
        except Exception:
            return 0

        applied = 0
        for skill in skills:
            skill_id = str(skill.get("id", "")).strip()
            if not skill_id:
                continue
            applies_to = skill.get("applies_to_tools", [])
            if not isinstance(applies_to, list):
                applies_to = []
            triggers = skill.get("triggers", [])
            if not isinstance(triggers, list):
                triggers = []
            for tool_id in applies_to:
                tool_key = str(tool_id or "").strip()
                if not tool_key:
                    continue
                with self._lock:
                    tool_def = self._tools.get(tool_key)
                    if tool_def is None:
                        continue
                    skills_list = list(tool_def.get("skills", []) or [])
                    if skill_id not in skills_list:
                        skills_list.append(skill_id)
                    tool_def["skills"] = skills_list
                    metadata = dict(tool_def.get("metadata", {}))
                    metadata_skills = list(metadata.get("skills", []) or [])
                    if skill_id not in metadata_skills:
                        metadata_skills.append(skill_id)
                    metadata["skills"] = metadata_skills
                    if triggers:
                        metadata["skill_triggers"] = [
                            *list(metadata.get("skill_triggers", []) or []),
                            *(str(trigger) for trigger in triggers if str(trigger).strip()),
                        ]
                    tool_def["metadata"] = metadata
                    self._tools[tool_key] = tool_def
                applied += 1
        return applied

    @staticmethod
    def _tool_from_manifest(manifest):
        config = manifest.get("config", {}) or {}
        tool_id = str(config.get("tool_id", manifest.get("id", ""))).strip()
        if not tool_id:
            return None
        ui = config.get("ui")
        if not isinstance(ui, dict):
            ui = manifest.get("ui")
        if not isinstance(ui, dict):
            ui = {}
        execution = dict(config.get("execution", {}))
        handler = str(config.get("handler", "")).strip()
        write_action = bool(config.get("write_action", False))
        requires_approval = bool(config.get("requires_approval", False))
        action_type = str(config.get("action_type", "")).strip()
        risk = str(config.get("risk", manifest.get("risk", "")) or "").strip().lower()
        if not risk:
            risk = "high" if write_action or requires_approval or action_type in {"write", "execute", "delete"} else "low"
        if risk not in {"low", "medium", "high"}:
            risk = "low"
        tags = list(config.get("tags", manifest.get("tags", [])) or [])
        if risk == "high" and "danger" not in tags:
            tags.append("danger")
        if not execution:
            execution = {"type": "local"}
        if handler and "handler" not in execution:
            execution["handler"] = handler
        return {
            "tool_id": tool_id,
            "name": str(config.get("name", tool_id)),
            "summary": str(config.get("summary", manifest.get("description", ""))),
            "tags": tags,
            "risk": risk,
            "schema": dict(
                config.get(
                    "schema",
                    {
                        "parameters": {
                            "type": "object",
                            "properties": {},
                            "required": [],
                        }
                    },
                )
            ),
            "execution": execution,
            "category": str(config.get("tool_category", config.get("category", ""))),
            "action_type": action_type,
            "write_action": write_action,
            "requires_approval": requires_approval,
            "ui": dict(ui),
            "metadata": {
                "source": "extension",
                "manifest_path": manifest.get("source_path", ""),
                "source_pack_id": manifest.get("source_pack_id", ""),
                "category": str(config.get("tool_category", config.get("category", ""))),
                "action_type": action_type,
                "write_action": write_action,
                "requires_approval": requires_approval,
                "risk": risk,
            },
        }

    # ------------------------------------------------------------------
    # dynamic tools — persistence
    # ------------------------------------------------------------------

    def _load_dynamic_tools(self):
        """起動時に user_data/shared/tools/ から動的ツール定義を読み込む"""
        if not os.path.isdir(self._tools_dir):
            return
        for fname in os.listdir(self._tools_dir):
            if not fname.endswith(".tool.json"):
                continue
            fpath = os.path.join(self._tools_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    tool_def = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue
            # handler_code があればファイルから読み込み
            name = tool_def.get("name", "")
            handler_path = os.path.join(self._tools_dir, name + ".handler.py")
            if os.path.isfile(handler_path):
                try:
                    with open(handler_path, "r", encoding="utf-8") as f:
                        tool_def["handler_code"] = f.read()
                except OSError:
                    pass
            with self._lock:
                self._tools[tool_def["tool_id"]] = tool_def

    def _save_tool_json(self, tool_def):
        """ツール定義を JSON ファイルに保存する"""
        name = tool_def.get("name", tool_def.get("tool_id", "unknown"))
        fpath = os.path.join(self._tools_dir, name + ".tool.json")
        # handler_code はファイル分離するので JSON には含めない
        save_def = {k: v for k, v in tool_def.items() if k != "handler_code"}
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(save_def, f, ensure_ascii=False, indent=2)

    def _save_handler_code(self, name, code):
        """handler コードを .handler.py ファイルに保存する"""
        fpath = os.path.join(self._tools_dir, name + ".handler.py")
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(code)

    def _delete_tool_files(self, name):
        """ツール定義ファイルと handler コードファイルを削除する"""
        json_path = os.path.join(self._tools_dir, name + ".tool.json")
        handler_path = os.path.join(self._tools_dir, name + ".handler.py")
        if os.path.isfile(json_path):
            os.remove(json_path)
        if os.path.isfile(handler_path):
            os.remove(handler_path)

    # ------------------------------------------------------------------
    # core CRUD
    # ------------------------------------------------------------------

    def register(self, tool_def):
        """ツール定義を登録（インメモリのみ、永続化なし）"""
        with self._lock:
            self._tools[tool_def["tool_id"]] = tool_def

    def unregister(self, tool_name):
        """ツール定義を削除（インメモリのみ）"""
        with self._lock:
            self._tools.pop(tool_name, None)

    def get(self, tool_name):
        """ツール定義を取得"""
        with self._lock:
            return self._tools.get(tool_name)

    def list_tools(self, filter_dict=None):
        """登録済みツール一覧を返す"""
        with self._lock:
            tools = list(self._tools.values())
        if filter_dict and "tags" in filter_dict:
            required_tags = set(filter_dict["tags"])
            tools = [t for t in tools if required_tags & set(t.get("tags", []))]
        return tools

    def get_schema(self, tool_name):
        """ツールのスキーマを取得"""
        with self._lock:
            tool = self._tools.get(tool_name)
        if tool:
            return tool.get("schema", {})
        return None

    # ------------------------------------------------------------------
    # dynamic tool operations (with persistence)
    # ------------------------------------------------------------------

    def register_dynamic(self, tool_def, handler_code=None):
        """
        動的ツールを登録し永続化する。
        tool_def: ツール定義 dict（tool_id, name, summary, tags, schema, execution 等）
        handler_code: Python コード文字列（None なら保存しない）
        戻り値: 登録された tool_def
        """
        # execution.type を dynamic に設定
        if "execution" not in tool_def:
            tool_def["execution"] = {}
        tool_def["execution"]["type"] = "dynamic"

        if handler_code is not None:
            tool_def["handler_code"] = handler_code

        with self._lock:
            self._tools[tool_def["tool_id"]] = tool_def

        # 永続化
        self._save_tool_json(tool_def)
        if handler_code is not None:
            self._save_handler_code(tool_def["name"], handler_code)

        return tool_def

    def update_dynamic(self, tool_name, updates):
        """
        動的ツール定義を部分更新し永続化する。
        tool_name: ツール名（tool_id と同じ）
        updates: 部分更新 dict
        戻り値: 更新後の tool_def、見つからなければ None
        """
        with self._lock:
            tool_def = self._tools.get(tool_name)
            if tool_def is None:
                return None
            # execution.type が dynamic でなければ更新不可
            exec_type = tool_def.get("execution", {}).get("type", "")
            if exec_type != "dynamic":
                return None
            # 部分更新
            handler_code = updates.pop("handler_code", None)
            for key, value in updates.items():
                if key == "schema" and isinstance(value, dict) and isinstance(tool_def.get("schema"), dict):
                    tool_def["schema"].update(value)
                elif key == "tags" and isinstance(value, list):
                    tool_def["tags"] = value
                else:
                    tool_def[key] = value
            if handler_code is not None:
                tool_def["handler_code"] = handler_code
            self._tools[tool_name] = tool_def

        # 永続化
        self._save_tool_json(tool_def)
        if handler_code is not None:
            self._save_handler_code(tool_def["name"], handler_code)

        return tool_def

    def unregister_dynamic(self, tool_name):
        """
        動的ツールを削除し、ファイルも削除する。
        戻り値: 削除された tool_def、見つからなければ None
        """
        with self._lock:
            tool_def = self._tools.get(tool_name)
            if tool_def is None:
                return None
            exec_type = tool_def.get("execution", {}).get("type", "")
            if exec_type != "dynamic":
                return None
            self._tools.pop(tool_name, None)

        self._delete_tool_files(tool_name)
        return tool_def

    def export_tool(self, tool_name):
        """
        ツール定義を export 用の dict として返す。
        handler_code も含める。
        戻り値: dict or None
        """
        with self._lock:
            tool_def = self._tools.get(tool_name)
        if tool_def is None:
            return None
        export = dict(tool_def)
        # handler_code がインメモリになければファイルから読む
        if "handler_code" not in export:
            name = export.get("name", "")
            handler_path = os.path.join(self._tools_dir, name + ".handler.py")
            if os.path.isfile(handler_path):
                try:
                    with open(handler_path, "r", encoding="utf-8") as f:
                        export["handler_code"] = f.read()
                except OSError:
                    pass
        return export

    # ------------------------------------------------------------------
    # MCP
    # ------------------------------------------------------------------

    def register_mcp_server(self, server_name, connection_info):
        """MCP サーバー接続情報を記録"""
        with self._lock:
            self._mcp_servers[server_name] = connection_info

    def list_mcp_servers(self):
        """MCP サーバー一覧"""
        with self._lock:
            return dict(self._mcp_servers)
