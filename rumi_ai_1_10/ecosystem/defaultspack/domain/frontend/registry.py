from __future__ import annotations

import base64
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from domain.ai_client.client import AIClient
from domain.ai_client.api_key_store import provider_has_api_key, set_provider_api_key
from domain.capability.catalog import CapabilityCatalog
from domain.chat.store import ChatStore
from domain.dev.inspector import Inspector
from domain.extensions.runtime import get_extension_registry
from domain.tool.registry import ToolRegistry


class FrontendRegistry:
    """Registry for frontend catalog, settings, and chat preview metadata."""

    def __init__(self, pack_root: Path | None = None) -> None:
        self._pack_root = pack_root or Path(__file__).resolve().parents[2]
        self._extensions_dir = self._pack_root / "user_data" / "shared" / "frontend_extensions"
        self._shell_path = self._pack_root / "user_data" / "shared" / "frontend_shell.json"
        self._settings_path = self._pack_root / "user_data" / "shared" / "frontend_settings.json"

    def build_catalog(self) -> dict[str, Any]:
        self._load_diagnostics: list[dict[str, Any]] = []
        extensions = self._load_extensions()
        ui_surfaces = self._load_ui_surfaces()
        shell = self._shell(ui_surfaces, extensions)
        parts = self._parts(ui_surfaces, extensions)
        component_bindings = self._component_bindings(ui_surfaces, extensions)
        return {
            "app": self._app_metadata(ui_surfaces),
            "agent_service": CapabilityCatalog(self._pack_root).manifest(),
            "shell": shell,
            "parts": parts,
            "component_bindings": component_bindings,
            "sidebar": {
                "filters": self._sidebar_filters(),
                "items": self._sidebar_items(ui_surfaces, extensions),
            },
            "settings": {
                "sections": self._settings_sections(ui_surfaces, extensions),
                "values": self._read_settings(),
            },
            "chat_rendering": {
                "renderers": self._chat_renderers(ui_surfaces, extensions),
            },
            "extension_points": self._extension_points(),
            "diagnostics": self._diagnostics(shell, parts, component_bindings),
        }

    def get_settings(self) -> dict[str, Any]:
        ui_surfaces = self._load_ui_surfaces()
        return {
            "sections": self._settings_sections(ui_surfaces, self._load_extensions()),
            "values": self._read_settings(),
        }

    def update_settings(self, patch: dict[str, Any] | None) -> dict[str, Any]:
        current = self._read_settings()
        sanitized_patch = self._sanitize_settings_patch(patch or {})
        merged = self._deep_merge(current, sanitized_patch)
        merged = self._refresh_derived_settings(merged)
        self._settings_path.parent.mkdir(parents=True, exist_ok=True)
        self._settings_path.write_text(
            json.dumps(merged, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return merged

    def build_conversation_preview(self, conversation_id: str) -> dict[str, Any]:
        store = ChatStore()
        conversation = store.get_conversation(conversation_id)
        if conversation is None:
            raise KeyError(conversation_id)

        inspector = Inspector()
        preview_items: list[dict[str, Any]] = []
        latest_log = inspector.find_by_conversation(conversation_id, limit=1)
        if latest_log:
            preview_items.extend(self._preview_from_log(latest_log[0]))

        for message in conversation.get("messages", [])[-6:]:
            preview_items.extend(self._preview_from_message(message))

        preview_items.sort(key=lambda item: item.get("timestamp", 0), reverse=True)
        return {
            "conversation_id": conversation_id,
            "previews": preview_items[:20],
            "summary": {
                "messages": len(conversation.get("messages", [])),
                "preview_count": len(preview_items[:20]),
            },
        }

    def _sidebar_filters(self) -> list[dict[str, str]]:
        return [
            {"id": "all", "label": "All"},
            {"id": "tool", "label": "Tools"},
            {"id": "widget", "label": "Widgets"},
            {"id": "system", "label": "System"},
            {"id": "integration", "label": "Integrations"},
            {"id": "capability", "label": "Capabilities"},
        ]

    def _app_metadata(self, ui_surfaces: list[dict[str, Any]]) -> dict[str, Any]:
        app: dict[str, Any] = {
            "id": "defaultspack",
            "name": "Rumi Defaultspack",
            "icon": "/static/assets/icons/defaultspack-icon.png",
            "account": self._rumi_account_metadata(),
        }
        for surface in ui_surfaces:
            config = surface.get("config", {})
            if isinstance(config, dict) and isinstance(config.get("app"), dict):
                app = self._deep_merge(app, config["app"])
        return app

    def _rumi_root(self) -> Path:
        return self._pack_root.parents[1]

    def _rumi_account_metadata(self) -> dict[str, Any]:
        account: dict[str, Any] = {
            "display_name": "Rumi",
            "email": "",
            "plan_label": "Local Account",
            "avatar_url": "",
            "initial": "R",
            "source": "fallback",
        }
        token_payload = self._read_rumi_oauth_payload()
        profile = self._read_rumi_profile()
        user_metadata = token_payload.get("user_metadata", {}) if isinstance(token_payload, dict) else {}
        app_metadata = token_payload.get("app_metadata", {}) if isinstance(token_payload, dict) else {}
        email = str(token_payload.get("email") or user_metadata.get("email") or "").strip()
        display_name = str(
            profile.get("username")
            or user_metadata.get("full_name")
            or user_metadata.get("name")
            or token_payload.get("name")
            or ""
        ).strip()
        if not display_name and email:
            display_name = email.split("@", 1)[0]
        avatar_url = str(
            profile.get("icon")
            or user_metadata.get("avatar_url")
            or user_metadata.get("picture")
            or token_payload.get("picture")
            or ""
        ).strip()
        plan_label = str(
            profile.get("plan")
            or profile.get("subscription_plan")
            or token_payload.get("plan")
            or token_payload.get("subscription_plan")
            or app_metadata.get("plan")
            or app_metadata.get("subscription_plan")
            or "Rumi Account"
        ).strip()
        if display_name:
            account["display_name"] = display_name
        if email:
            account["email"] = email
        if avatar_url:
            account["avatar_url"] = avatar_url
        if plan_label:
            account["plan_label"] = plan_label
        account["initial"] = str(account["display_name"] or account["email"] or "R")[0].upper()
        account["source"] = "rumi_profile" if profile else ("rumi_oauth" if token_payload else "fallback")
        return account

    def _read_rumi_profile(self) -> dict[str, Any]:
        profile_path = self._rumi_root() / "user_data" / "settings" / "profile.json"
        try:
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            return profile if isinstance(profile, dict) else {}
        except Exception:
            return {}

    def _read_rumi_oauth_payload(self) -> dict[str, Any]:
        token_path = self._rumi_root() / "user_data" / "settings" / "oauth_tokens.json"
        try:
            token_data = json.loads(token_path.read_text(encoding="utf-8"))
            token = str(token_data.get("access_token", ""))
            payload_segment = token.split(".")[1]
            padding = "=" * (-len(payload_segment) % 4)
            decoded = base64.urlsafe_b64decode((payload_segment + padding).encode("ascii"))
            payload = json.loads(decoded.decode("utf-8"))
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def _shell(
        self,
        ui_surfaces: list[dict[str, Any]],
        extensions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        shell = {
            "layout": {
                "id": "default_chat_shell",
                "regions": [
                    {"id": "title_bar", "part_id": "app_chrome", "renderer": "title_bar", "slot": "top", "order": 10, "enabled": True},
                    {"id": "history", "part_id": "conversation_history", "renderer": "history_board", "slot": "left", "order": 20, "enabled": True},
                    {"id": "chat_header", "part_id": "ai_chat", "renderer": "chat_header", "slot": "main", "order": 30, "enabled": True},
                    {"id": "chat_messages", "part_id": "ai_chat", "renderer": "chat_messages", "slot": "main", "order": 40, "enabled": True},
                    {"id": "composer", "part_id": "ai_chat", "renderer": "composer", "slot": "bottom", "order": 50, "enabled": True},
                    {"id": "activity_preview", "part_id": "activity_preview", "renderer": "activity_preview", "slot": "right", "order": 60, "enabled": True},
                    {"id": "right_sidebar", "part_id": "extension_sidebar", "renderer": "right_sidebar", "slot": "right", "order": 70, "enabled": True},
                    {"id": "settings_modal", "part_id": "settings", "renderer": "settings_modal", "slot": "overlay", "order": 80, "enabled": True},
                ],
            },
            "renderers": [
                {"id": "title_bar", "component": "TitleBar", "regions": ["title_bar"], "fallback": "hidden"},
                {"id": "history_board", "component": "HistoryBoard", "regions": ["history"], "fallback": "hidden"},
                {"id": "chat_header", "component": "ChatHeader", "regions": ["chat_header"], "fallback": "hidden"},
                {"id": "chat_messages", "component": "ChatMessages", "regions": ["chat_messages"], "fallback": "plain_text"},
                {"id": "composer", "component": "Composer", "regions": ["composer"], "fallback": "hidden"},
                {"id": "activity_preview", "component": "ToolPreviewPanel", "regions": ["activity_preview"], "fallback": "hidden"},
                {"id": "right_sidebar", "component": "RightSidebar", "regions": ["right_sidebar"], "fallback": "hidden"},
                {"id": "settings_modal", "component": "SettingsModal", "regions": ["settings_modal"], "fallback": "hidden"},
            ],
        }
        user_shell = self._load_shell_config()
        for manifest in [*ui_surfaces, user_shell, *extensions]:
            config = manifest.get("config", manifest)
            if not isinstance(config, dict):
                continue
            if isinstance(config.get("shell_layout"), dict):
                shell["layout"] = self._deep_merge(shell["layout"], config["shell_layout"])
            renderers = config.get("shell_renderers")
            if isinstance(renderers, list):
                shell["renderers"] = self._dedupe_by_key(
                    [*shell["renderers"], *(item for item in renderers if isinstance(item, dict))],
                    "id",
                )
        return shell

    def _parts(
        self,
        ui_surfaces: list[dict[str, Any]],
        extensions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        parts: list[dict[str, Any]] = [
            {
                "id": "app_chrome",
                "kind": "shell",
                "label": "App Chrome",
                "uses": ["frontend"],
                "schema": {"type": "object", "properties": {"app": {"type": "object"}, "shell": {"type": "object"}}},
            },
            {
                "id": "conversation_history",
                "kind": "navigation",
                "label": "Conversation History",
                "uses": ["chat"],
                "contracts": {"conversations": "/api/chat/conversations"},
                "schema": {"type": "object", "properties": {"items": {"type": "array"}, "active_id": {"type": ["string", "null"]}}},
            },
            {
                "id": "ai_chat",
                "kind": "chat",
                "label": "AI Chat",
                "uses": ["chat", "ai_client", "prompt", "memory", "tool", "frontend"],
                "contracts": {
                    "conversation": "/api/chat/conversations",
                    "catalog": "/api/ui/catalog",
                    "settings": "/api/ui/settings",
                },
                "schema": {
                    "type": "object",
                    "required": ["conversation", "messages"],
                    "properties": {
                        "conversation": {"type": ["object", "null"]},
                        "messages": {"type": "array"},
                        "composer": {"type": "object"},
                    },
                },
            },
            {
                "id": "activity_preview",
                "kind": "preview",
                "label": "Activity Preview",
                "uses": ["chat", "dev", "tool", "knowledge", "memory", "media", "artifact", "research", "browser", "computer", "collaboration"],
                "contracts": {
                    "preview": "/api/ui/conversations/{conversation_id}/preview",
                },
                "schema": {
                    "type": "object",
                    "properties": {
                        "tool_timeline": {"type": "array"},
                        "plan_steps": {"type": "array"},
                        "approvals": {"type": "array"},
                        "attachments": {"type": "array"},
                        "audio": {"type": "array"},
                    },
                },
            },
            {
                "id": "extension_sidebar",
                "kind": "sidebar",
                "label": "Extension Sidebar",
                "uses": ["tool", "widget", "frontend", "artifact", "research", "browser", "computer", "scheduler", "collaboration", "share"],
                "contracts": {"catalog": "/api/ui/catalog", "settings": "/api/ui/settings"},
                "schema": {"type": "object", "properties": {"items": {"type": "array"}, "filters": {"type": "array"}}},
            },
            {
                "id": "settings",
                "kind": "settings",
                "label": "Settings",
                "uses": ["frontend"],
                "contracts": {"settings": "/api/ui/settings"},
                "schema": {"type": "object", "properties": {"sections": {"type": "array"}, "values": {"type": "object"}}},
            },
        ]
        parts.extend(self._config_list(ui_surfaces, "parts"))
        parts.extend(self._config_list(extensions, "parts"))
        return self._dedupe_by_key(parts, "id")

    def _component_bindings(
        self,
        ui_surfaces: list[dict[str, Any]],
        extensions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        bindings: list[dict[str, Any]] = [
            {
                "part_id": "ai_chat",
                "component": "chat",
                "requires": ["ai_client"],
                "optional": ["prompt", "memory", "tool", "agent"],
            }
        ]
        bindings.extend(self._config_list(ui_surfaces, "component_bindings"))
        bindings.extend(self._config_list(extensions, "component_bindings"))
        return self._dedupe_by_key(bindings, "part_id")

    def _sidebar_items(
        self,
        ui_surfaces: list[dict[str, Any]],
        extensions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        registry = ToolRegistry()
        items: list[dict[str, Any]] = []

        for tool in registry.list_tools():
            schema = tool.get("schema", {}).get("parameters", {})
            execution_type = tool.get("execution", {}).get("type", "local")
            items.append(
                {
                    "id": tool.get("tool_id", tool.get("name", "tool")),
                    "label": tool.get("name", tool.get("tool_id", "tool")),
                    "category": "tool",
                    "description": tool.get("summary", ""),
                    "badge": "Dynamic" if execution_type == "dynamic" else None,
                    "tags": tool.get("tags", []),
                    "ui": dict(tool.get("ui", {})) if isinstance(tool.get("ui"), dict) else {},
                    "origin": {"kind": "tool_registry", "path": "domain/tool/registry.py"},
                    "panel": {
                        "kind": "schema",
                        "title": tool.get("name", tool.get("tool_id", "tool")),
                        "fields": self._schema_to_fields(schema),
                        "notes": [
                            "Tool schema is read from ToolRegistry.",
                            "Add or update tools under user_data/shared/tools/ via API.",
                        ],
                    },
                }
            )

        items.extend(
            [
                {
                    "id": "agent-service-capabilities",
                    "label": "Capabilities",
                    "category": "system",
                    "description": "defaultspack の local-first capability catalog。",
                    "tags": ["agent", "capability", "local-first"],
                    "origin": {"kind": "builtin", "path": "capabilities/"},
                    "panel": {
                        "kind": "info",
                        "title": "Agent Service Capabilities",
                        "notes": [
                            "/api/capabilities と /api/agent-service/manifest で同じ定義を取得できます。",
                            "capability yaml は他 pack から置き換え可能な標準語彙です。",
                        ],
                    },
                },
                {
                    "id": "knowledge-context",
                    "label": "Knowledge",
                    "category": "widget",
                    "description": "会話時に注入される knowledge 検索結果。",
                    "tags": ["knowledge", "preview"],
                    "origin": {"kind": "builtin", "path": "blocks/chat/_context_helpers.py"},
                    "panel": {
                        "kind": "info",
                        "title": "Knowledge Context",
                        "notes": [
                            "Conversation preview で knowledge_results を表示します。",
                            "検索実装は blocks/chat/_context_helpers.py にあります。",
                        ],
                    },
                },
                {
                    "id": "artifacts",
                    "label": "Artifacts",
                    "category": "widget",
                    "description": "生成物と添付物を共通 artifact contract で扱います。",
                    "tags": ["artifact", "preview", "export"],
                    "origin": {"kind": "builtin", "path": "domain/artifact/store.py"},
                    "panel": {
                        "kind": "actions",
                        "title": "Artifacts",
                        "actions": [
                            {"id": "artifacts.list", "label": "List Artifacts", "icon": "artifacts"},
                        ],
                        "notes": [
                            "/api/artifacts は UI preview と share/export の共通ソースです。",
                            "個別 renderer ではなく汎用 artifact item として扱えます。",
                        ],
                    },
                },
                {
                    "id": "research-providers",
                    "label": "Research",
                    "category": "integration",
                    "description": "local / external web / Reddit を同じ source schema で扱います。",
                    "tags": ["research", "web", "reddit"],
                    "origin": {"kind": "builtin", "path": "domain/research/providers.py"},
                    "panel": {
                        "kind": "actions",
                        "title": "Research Providers",
                        "actions": [
                            {"id": "research.web", "label": "Web Provider Dry Run", "icon": "web"},
                            {"id": "research.reddit", "label": "Reddit Provider Dry Run", "icon": "reddit"},
                        ],
                        "notes": [
                            "右サイドバーからは安全のため network disabled の dry-run を起動します。",
                            "API では allow_network=true を明示した場合に外部 provider を使います。",
                        ],
                    },
                },
                {
                    "id": "browser-computer",
                    "label": "Browser / Computer",
                    "category": "capability",
                    "description": "ブラウザ URL、session、承認済み desktop action を扱う controller。",
                    "tags": ["browser", "computer", "approval"],
                    "origin": {"kind": "builtin", "path": "domain/tool/browser_computer.py"},
                    "panel": {
                        "kind": "actions",
                        "title": "Browser / Computer",
                        "actions": [
                            {"id": "browser.session", "label": "Inspect Browser Session", "icon": "browser"},
                            {"id": "browser.screenshot.dry_run", "label": "Screenshot Dry Run", "icon": "browser"},
                        ],
                        "notes": [
                            "実操作は approved=true が必要です。UI の既定 action は dry-run です。",
                            "同じ controller に open_url/click/type/key/scroll を追加できます。",
                        ],
                    },
                },
                {
                    "id": "scheduled-tasks",
                    "label": "Schedules",
                    "category": "system",
                    "description": "agent schedule store と scheduler route。",
                    "tags": ["agent", "schedule"],
                    "origin": {"kind": "builtin", "path": "domain/agent/scheduler.py"},
                    "panel": {
                        "kind": "actions",
                        "title": "Scheduled Tasks",
                        "actions": [
                            {"id": "schedules.list", "label": "List Schedules", "icon": "schedules"},
                        ],
                        "notes": [
                            "/api/agent/schedules で作成・更新・pause/resume・trigger が可能です。",
                        ],
                    },
                },
                {
                    "id": "collaboration",
                    "label": "Collaboration",
                    "category": "widget",
                    "description": "channel と multi-agent collaboration の UI entry。",
                    "tags": ["channel", "multi-agent", "collaboration"],
                    "origin": {"kind": "builtin", "path": "domain/agent/inter_agent_comm.py"},
                    "panel": {
                        "kind": "actions",
                        "title": "Collaboration",
                        "actions": [
                            {"id": "channels.list", "label": "List Channels", "icon": "channels"},
                        ],
                        "notes": [
                            "channel API は chat block、multi-agent API は agent block から提供されます。",
                        ],
                    },
                },
                {
                    "id": "share-export",
                    "label": "Share / Export",
                    "category": "integration",
                    "description": "会話 export と local share link を作成します。",
                    "tags": ["share", "export"],
                    "origin": {"kind": "builtin", "path": "domain/share/store.py"},
                    "panel": {
                        "kind": "actions",
                        "title": "Share / Export",
                        "actions": [
                            {"id": "conversation.export", "label": "Export Active Conversation", "icon": "export", "payload": {"format": "markdown"}},
                            {"id": "conversation.share", "label": "Create Local Share Link", "icon": "share"},
                        ],
                        "notes": [
                            "share はローカル token store に保存され、/api/share/{token} で取得できます。",
                        ],
                    },
                },
                {
                    "id": "memory-context",
                    "label": "Memory",
                    "category": "system",
                    "description": "会話時に注入される memory 検索結果。",
                    "tags": ["memory", "preview"],
                    "origin": {"kind": "builtin", "path": "blocks/chat/_context_helpers.py"},
                    "panel": {
                        "kind": "info",
                        "title": "Memory Context",
                        "notes": [
                            "Conversation preview で memory_results を表示します。",
                            "MemoryStore の recall 結果をそのまま扱います。",
                        ],
                    },
                },
                {
                    "id": "request-inspector",
                    "label": "Inspector",
                    "category": "system",
                    "description": "直近リクエストの prompt / context / tool usage を参照。",
                    "tags": ["debug", "inspect"],
                    "origin": {"kind": "builtin", "path": "domain/dev/inspector.py"},
                    "panel": {
                        "kind": "info",
                        "title": "Inspector",
                        "notes": [
                            "blocks.dev.inspect からも同じログを取得できます。",
                            "会話 preview と settings の両方で再利用できます。",
                        ],
                    },
                },
                {
                    "id": "provider-catalog",
                    "label": "Providers",
                    "category": "integration",
                    "description": "現在利用可能な AI provider / model catalog。",
                    "tags": ["provider", "model"],
                    "origin": {"kind": "builtin", "path": "domain/ai_client/client.py"},
                    "panel": {
                        "kind": "models",
                        "title": "Providers",
                        "models": self._list_provider_models(),
                    },
                },
            ]
        )

        items.extend(self._config_list(ui_surfaces, "sidebar_items"))
        items.extend(self._config_list(extensions, "sidebar_items"))

        return self._dedupe_by_key(items, "id")

    def _settings_sections(
        self,
        ui_surfaces: list[dict[str, Any]],
        extensions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        sections = [
            {
                "id": "general",
                "label": "General",
                "description": "defaultspack shell behavior shared across the app.",
                "fields": [
                    {
                        "id": "composer_placeholder",
                        "label": "Composer Placeholder",
                        "type": "text",
                        "default": "メッセージを入力...",
                        "help": "チャット入力欄の placeholder。",
                    },
                    {
                        "id": "show_activity_in_messages",
                        "label": "Activity In Chat",
                        "type": "toggle",
                        "default": True,
                        "help": "assistant メッセージ上部に activity 情報を表示する。",
                    },
                ],
            },
            {
                "id": "preview",
                "label": "Preview",
                "description": "右 preview pane と activity feed の挙動。",
                "fields": [
                    {"id": "auto_open", "label": "Auto Open", "type": "toggle", "default": False},
                    {
                        "id": "default_mode",
                        "label": "Preview Mode",
                        "type": "select",
                        "default": "auto",
                        "options": [
                            {"value": "auto", "label": "Auto"},
                            {"value": "manual", "label": "Manual"},
                        ],
                    },
                    {
                        "id": "max_items",
                        "label": "Preview Limit",
                        "type": "number",
                        "default": 12,
                        "min": 1,
                        "max": 50,
                    },
                ],
            },
            {
                "id": "chat_rendering",
                "label": "Chat Rendering",
                "description": "block / widget rendering rules for the conversation pane.",
                "fields": [
                    {"id": "render_markdown", "label": "Render Markdown", "type": "toggle", "default": True},
                    {"id": "show_widgets", "label": "Render Widgets", "type": "toggle", "default": True},
                    {
                        "id": "unknown_block_strategy",
                        "label": "Unknown Block Strategy",
                        "type": "select",
                        "default": "json",
                        "options": [
                            {"value": "json", "label": "JSON Fallback"},
                            {"value": "hidden", "label": "Hide"},
                            {"value": "text", "label": "Plain Text"},
                        ],
                    },
                ],
            },
            {
                "id": "models",
                "label": "Models & Providers",
                "description": "AI provider, default model, and model profile settings.",
                "fields": [
                    {
                        "id": "detected_provider_count",
                        "label": "Detected Providers",
                        "type": "readonly",
                        "default": len(self._list_provider_models()),
                    },
                    {
                        "id": "preferred_model",
                        "label": "Preferred Model",
                        "type": "text",
                        "default": "openrouter/tencent/hy3-preview:free",
                        "options": self._model_options(),
                        "help": "新しい会話に渡す model。例: openrouter/tencent/hy3-preview:free",
                    },
                    {
                        "id": "favorite_profiles",
                        "label": "Favorite Profiles",
                        "type": "textarea",
                        "default": "openrouter/tencent/hy3-preview:free\nstub/default",
                        "help": "Composer に表示する profile_id を改行または JSON 配列で保存します。",
                    },
                    {
                        "id": "thinking_level_by_profile",
                        "label": "Thinking Levels",
                        "type": "textarea",
                        "default": '{"openrouter/tencent/hy3-preview:free":"medium"}',
                        "help": "profile_id ごとの thinking level。未対応モデルでは無視されます。",
                    },
                    {
                        "id": "model_profile",
                        "label": "Model Profile",
                        "type": "textarea",
                        "default": self._default_model_profile_text(),
                        "help": "モデルの特性メモ。routing/profile API とつなぐ前の editable contract として保存します。",
                    },
                    {
                        "id": "openrouter_api_key",
                        "label": "OpenRouter API Key",
                        "type": "secret",
                        "default": "",
                        "provider_id": "openrouter",
                        "configured_field": "openrouter_api_key_configured",
                        "help": "保存後も値は再表示されません。",
                    },
                    {
                        "id": "openrouter_api_key_configured",
                        "label": "OpenRouter Key Saved",
                        "type": "readonly",
                        "default": provider_has_api_key("openrouter", pack_root=self._pack_root),
                    },
                ],
            },
            {
                "id": "research",
                "label": "Research",
                "description": "External provider behavior shared by research tools.",
                "fields": [
                    {"id": "allow_external_network", "label": "External Network", "type": "toggle", "default": False, "help": "Web/Reddit provider を実ネットワークに接続する既定値。"},
                    {"id": "default_limit", "label": "Default Limit", "type": "number", "default": 5, "min": 1, "max": 50},
                ],
            },
            {
                "id": "browser_computer",
                "label": "Browser / Computer",
                "description": "Approval defaults for browser and desktop control.",
                "fields": [
                    {"id": "dry_run_by_default", "label": "Dry Run By Default", "type": "toggle", "default": True},
                    {"id": "require_approval", "label": "Require Approval", "type": "toggle", "default": True},
                ],
            },
            {
                "id": "collaboration",
                "label": "Collaboration",
                "description": "Channel and multi-agent UI defaults.",
                "fields": [
                    {"id": "show_channel_events", "label": "Show Channel Events", "type": "toggle", "default": True},
                    {"id": "default_visibility", "label": "Default Visibility", "type": "select", "default": "local", "options": [{"value": "local", "label": "Local"}, {"value": "private", "label": "Private"}, {"value": "unlisted", "label": "Unlisted"}]},
                ],
            },
            {
                "id": "share",
                "label": "Share & Export",
                "description": "Local share link and export defaults.",
                "fields": [
                    {"id": "default_format", "label": "Default Format", "type": "select", "default": "markdown", "options": [{"value": "markdown", "label": "Markdown"}, {"value": "json", "label": "JSON"}]},
                    {"id": "copy_result_to_clipboard", "label": "Copy Result", "type": "toggle", "default": True},
                ],
            },
        ]

        sections.extend(self._config_list(ui_surfaces, "settings_sections"))
        sections.extend(self._config_list(extensions, "settings_sections"))

        return sections

    def _chat_renderers(
        self,
        ui_surfaces: list[dict[str, Any]],
        extensions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        renderers = [
            {"id": "text", "block_types": ["text", "markdown"], "component": "MarkdownBlock", "fallback": "plain_text"},
            {"id": "code", "block_types": ["code"], "component": "CodeBlock", "fallback": "plain_text"},
            {"id": "image", "block_types": ["image"], "component": "ImageBlock", "fallback": "link"},
            {"id": "widget", "block_types": [], "widget_types": ["*"], "component": "WidgetCard", "fallback": "json"},
        ]

        renderers.extend(self._config_list(ui_surfaces, "chat_renderers"))
        renderers.extend(self._config_list(extensions, "chat_renderers"))

        return self._dedupe_by_key(renderers, "id")

    def _extension_points(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "parts",
                "path": "extensions/ui/*/manifest.json config.parts",
                "description": "Small frontend parts and the component contracts they use.",
            },
            {
                "id": "component_bindings",
                "path": "extensions/ui/*/manifest.json config.component_bindings",
                "description": "Declarative component-to-part usage rules.",
            },
            {
                "id": "sidebar_items",
                "path": "user_data/shared/frontend_extensions/*.ui.json",
                "description": "Right sidebar entries and their panel metadata.",
            },
            {
                "id": "settings_sections",
                "path": "user_data/shared/frontend_extensions/*.ui.json",
                "description": "Settings modal sections / fields. Saved into frontend_settings.json.",
            },
            {
                "id": "chat_renderers",
                "path": "user_data/shared/frontend_extensions/*.ui.json",
                "description": "Metadata describing custom block/widget renderers.",
            },
            {
                "id": "composer.inline",
                "path": "user_data/shared/frontend_extensions/*.ui.json config.composer.inline",
                "description": "Small action buttons rendered inside the composer control row.",
            },
            {
                "id": "composer.below",
                "path": "user_data/shared/frontend_extensions/*.ui.json config.composer.below",
                "description": "Secondary action buttons rendered below the composer.",
            },
            {
                "id": "chat.activity",
                "path": "chat message events/tool_logs",
                "description": "Provider/tool activity records rendered in message history.",
            },
            {
                "id": "shell_layout",
                "path": "extensions/ui/*/manifest.json config.shell_layout or user_data/shared/frontend_shell.json",
                "description": "Declarative layout regions for the replaceable shell.",
            },
            {
                "id": "shell_renderers",
                "path": "extensions/ui/*/manifest.json config.shell_renderers or user_data/shared/frontend_extensions/*.ui.json",
                "description": "Renderer IDs and component names bound to shell regions.",
            },
        ]

    def _preview_from_log(self, log: dict[str, Any]) -> list[dict[str, Any]]:
        timestamp = self._iso_to_ms(log.get("timestamp"))
        items: list[dict[str, Any]] = []
        for tool_name in log.get("tools_called", []):
            items.append(
                {
                    "id": f"tool-{tool_name}-{timestamp}",
                    "toolStepId": tool_name,
                    "timestamp": timestamp,
                    "data": {
                        "type": "code",
                        "filename": tool_name,
                        "language": "text",
                        "content": f"Tool planned or referenced: {tool_name}",
                    },
                }
            )

        context_info = log.get("context_info", {})
        for index, item in enumerate(context_info.get("knowledge_results", []), start=1):
            items.append(
                {
                    "id": f"knowledge-{index}-{timestamp}",
                    "toolStepId": "knowledge",
                    "timestamp": timestamp - index,
                    "data": {
                        "type": "web",
                        "url": item.get("metadata", {}).get("source", ""),
                        "title": item.get("metadata", {}).get("title", f"Knowledge #{index}"),
                        "snippet": item.get("content", ""),
                    },
                }
            )

        for index, item in enumerate(context_info.get("memory_results", []), start=1):
            items.append(
                {
                    "id": f"memory-{index}-{timestamp}",
                    "toolStepId": "memory",
                    "timestamp": timestamp - 100 - index,
                    "data": {
                        "type": "file",
                        "filename": item.get("metadata", {}).get("source", f"memory-{index}.md"),
                        "size": f"score {item.get('score', 0):.2f}",
                        "content": item.get("content", ""),
                    },
                }
            )
        return items

    def _preview_from_message(self, message: dict[str, Any]) -> list[dict[str, Any]]:
        timestamp = int(message.get("created_at", 0))
        previews: list[dict[str, Any]] = []
        widget = message.get("widget")
        if isinstance(widget, dict):
            previews.append(
                {
                    "id": f"widget-{message.get('id')}",
                    "toolStepId": "widget",
                    "timestamp": timestamp,
                    "data": {
                        "type": "file",
                        "filename": f"widget:{widget.get('type', 'custom')}",
                        "size": "inline widget",
                        "content": json.dumps(widget, ensure_ascii=False, indent=2),
                    },
                }
            )

        content = message.get("content", [])
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        for index, block in enumerate(content):
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            if block_type == "image":
                previews.append(
                    {
                        "id": f"image-{message.get('id')}-{index}",
                        "toolStepId": "image",
                        "timestamp": timestamp - index,
                        "data": {
                            "type": "image",
                            "url": block.get("url", ""),
                            "alt": block.get("alt", "image"),
                            "prompt": block.get("prompt"),
                        },
                    }
                )
            elif block_type == "code":
                previews.append(
                    {
                        "id": f"code-{message.get('id')}-{index}",
                        "toolStepId": "code",
                        "timestamp": timestamp - index,
                        "data": {
                            "type": "code",
                            "filename": block.get("filename", "snippet"),
                            "language": block.get("language", "text"),
                            "content": block.get("text", ""),
                        },
                    }
                )
        return previews

    def _load_ui_surfaces(self) -> list[dict[str, Any]]:
        try:
            surfaces = get_extension_registry().ui_surfaces().list(enabled_only=True)
        except Exception:
            surfaces = []
        return [surface for surface in surfaces if isinstance(surface, dict)]

    def _load_extensions(self) -> list[dict[str, Any]]:
        if not self._extensions_dir.exists():
            return []
        extensions = []
        for path in sorted(self._extensions_dir.glob("*.ui.json")):
            try:
                extension = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(extension, dict):
                    extension["_source"] = str(path)
                    extensions.append(extension)
                else:
                    self._add_diagnostic("warning", "frontend_extension_not_object", f"{path} must contain a JSON object.", str(path))
            except (OSError, json.JSONDecodeError) as exc:
                self._add_diagnostic("warning", "frontend_extension_invalid_json", str(exc), str(path))
                continue
        return extensions

    def _load_shell_config(self) -> dict[str, Any]:
        if not self._shell_path.exists():
            return {}
        try:
            config = json.loads(self._shell_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            self._add_diagnostic("warning", "frontend_shell_invalid_json", str(exc), str(self._shell_path))
            return {}
        if not isinstance(config, dict):
            self._add_diagnostic("warning", "frontend_shell_not_object", "frontend_shell.json must contain a JSON object.", str(self._shell_path))
            return {}
        return config

    def _diagnostics(
        self,
        shell: dict[str, Any],
        parts: list[dict[str, Any]],
        component_bindings: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        diagnostics = list(getattr(self, "_load_diagnostics", []))

        part_ids = {str(part.get("id", "")).strip() for part in parts if str(part.get("id", "")).strip()}
        renderer_ids = {
            str(renderer.get("id", "")).strip()
            for renderer in shell.get("renderers", [])
            if isinstance(renderer, dict) and str(renderer.get("id", "")).strip()
        }

        seen_parts: set[str] = set()
        for index, part in enumerate(parts):
            part_id = str(part.get("id", "")).strip()
            source = str(part.get("_source", "catalog.parts"))
            if not part_id:
                diagnostics.append(self._diagnostic("warning", "part_missing_id", f"parts[{index}] is missing id.", source))
            elif part_id in seen_parts:
                diagnostics.append(self._diagnostic("warning", "part_duplicate_id", f"part id '{part_id}' is duplicated; the last definition wins.", source))
            seen_parts.add(part_id)
            if not isinstance(part.get("kind"), str) or not str(part.get("kind", "")).strip():
                diagnostics.append(self._diagnostic("warning", "part_missing_kind", f"part '{part_id or index}' is missing kind.", source))
            if "schema" in part and not isinstance(part.get("schema"), dict):
                diagnostics.append(self._diagnostic("warning", "part_invalid_schema", f"part '{part_id or index}' schema must be an object.", source))

        for index, binding in enumerate(component_bindings):
            source = str(binding.get("_source", "catalog.component_bindings"))
            part_id = str(binding.get("part_id", "")).strip()
            if not part_id:
                diagnostics.append(self._diagnostic("warning", "binding_missing_part_id", f"component_bindings[{index}] is missing part_id.", source))
            elif part_id not in part_ids:
                diagnostics.append(self._diagnostic("warning", "binding_unknown_part", f"component binding references unknown part '{part_id}'.", source))
            if not isinstance(binding.get("component"), str) or not str(binding.get("component", "")).strip():
                diagnostics.append(self._diagnostic("warning", "binding_missing_component", f"component binding for '{part_id or index}' is missing component.", source))
            for key in ("requires", "optional"):
                if key in binding and not isinstance(binding.get(key), list):
                    diagnostics.append(self._diagnostic("warning", f"binding_invalid_{key}", f"component binding '{part_id or index}' {key} must be a list.", source))

        layout = shell.get("layout", {})
        regions = layout.get("regions", []) if isinstance(layout, dict) else []
        if not isinstance(regions, list):
            diagnostics.append(self._diagnostic("warning", "shell_regions_not_list", "shell_layout.regions must be a list.", "catalog.shell.layout"))
            regions = []

        for index, region in enumerate(regions):
            if not isinstance(region, dict):
                diagnostics.append(self._diagnostic("warning", "shell_region_not_object", f"shell_layout.regions[{index}] must be an object.", "catalog.shell.layout"))
                continue
            region_id = str(region.get("id", "")).strip()
            part_id = str(region.get("part_id", "")).strip()
            renderer_id = str(region.get("renderer", "")).strip()
            source = str(region.get("_source", "catalog.shell.layout"))
            if not region_id:
                diagnostics.append(self._diagnostic("warning", "shell_region_missing_id", f"shell_layout.regions[{index}] is missing id.", source))
            if part_id and part_id not in part_ids:
                diagnostics.append(self._diagnostic("warning", "shell_region_unknown_part", f"region '{region_id or index}' references unknown part '{part_id}'.", source))
            if renderer_id and renderer_id not in renderer_ids:
                diagnostics.append(self._diagnostic("warning", "shell_region_unknown_renderer", f"region '{region_id or index}' references unknown renderer '{renderer_id}'.", source))
            if "order" in region and not isinstance(region.get("order"), (int, float)):
                diagnostics.append(self._diagnostic("warning", "shell_region_invalid_order", f"region '{region_id or index}' order must be numeric.", source))

        for index, renderer in enumerate(shell.get("renderers", [])):
            if not isinstance(renderer, dict):
                diagnostics.append(self._diagnostic("warning", "shell_renderer_not_object", f"shell.renderers[{index}] must be an object.", "catalog.shell.renderers"))
                continue
            renderer_id = str(renderer.get("id", "")).strip()
            source = str(renderer.get("_source", "catalog.shell.renderers"))
            if not renderer_id:
                diagnostics.append(self._diagnostic("warning", "shell_renderer_missing_id", f"shell.renderers[{index}] is missing id.", source))
            if not isinstance(renderer.get("component"), str) or not str(renderer.get("component", "")).strip():
                diagnostics.append(self._diagnostic("warning", "shell_renderer_missing_component", f"shell renderer '{renderer_id or index}' is missing component.", source))
            if "regions" in renderer and not isinstance(renderer.get("regions"), list):
                diagnostics.append(self._diagnostic("warning", "shell_renderer_invalid_regions", f"shell renderer '{renderer_id or index}' regions must be a list.", source))
            module = renderer.get("module")
            if module is not None and not self._is_trusted_renderer_module(module):
                diagnostics.append(self._diagnostic("warning", "shell_renderer_untrusted_module", f"shell renderer '{renderer_id or index}' module must be a trusted static renderer path.", source))
            if module is not None and renderer.get("trust") != "local":
                diagnostics.append(self._diagnostic("warning", "shell_renderer_missing_local_trust", f"shell renderer '{renderer_id or index}' module requires trust='local'.", source))

        return diagnostics

    def _is_trusted_renderer_module(self, module: Any) -> bool:
        if not isinstance(module, str):
            return False
        return module.startswith(("/static/renderers/", "/static/assets/renderers/", "/static/user_renderers/"))

    def _add_diagnostic(self, level: str, code: str, message: str, source: str) -> None:
        if not hasattr(self, "_load_diagnostics"):
            self._load_diagnostics = []
        self._load_diagnostics.append(self._diagnostic(level, code, message, source))

    def _diagnostic(self, level: str, code: str, message: str, source: str) -> dict[str, str]:
        return {"level": level, "code": code, "message": message, "source": source}

    def _config_list(self, manifests: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
        values: list[dict[str, Any]] = []
        for manifest in manifests:
            config = manifest.get("config", manifest)
            if not isinstance(config, dict):
                continue
            items = config.get(key, [])
            if not isinstance(items, list):
                continue
            values.extend(item for item in items if isinstance(item, dict))
        return values

    def _dedupe_by_key(self, items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
        deduped: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        for item in items:
            value = str(item.get(key, "")).strip()
            if not value:
                value = f"__index_{len(order)}"
            if value not in deduped:
                order.append(value)
            deduped[value] = item
        return [deduped[value] for value in order]

    def _read_settings(self) -> dict[str, Any]:
        values = self._default_settings()
        if self._settings_path.exists():
            try:
                saved = json.loads(self._settings_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                saved = {}
            values = self._deep_merge(values, saved)
        return self._refresh_derived_settings(values)

    def _default_settings(self) -> dict[str, Any]:
        return {
            "general": {"composer_placeholder": "メッセージを入力...", "show_activity_in_messages": True},
            "preview": {"auto_open": False, "default_mode": "auto", "max_items": 12},
            "chat_rendering": {"render_markdown": True, "show_widgets": True, "unknown_block_strategy": "json"},
            "models": {
                "detected_provider_count": len(self._list_provider_models()),
                "preferred_model": "openrouter/tencent/hy3-preview:free",
                "favorite_profiles": ["openrouter/tencent/hy3-preview:free", "stub/default"],
                "thinking_level_by_profile": {"openrouter/tencent/hy3-preview:free": "medium"},
                "model_profile": self._default_model_profile_text(),
                "openrouter_api_key": "",
                "openrouter_api_key_configured": provider_has_api_key("openrouter", pack_root=self._pack_root),
            },
        }

    def _model_options(self) -> list[dict[str, str]]:
        return [{"value": model["id"], "label": model["id"]} for model in self._list_provider_models()] or [
            {"value": "stub/default", "label": "stub/default"}
        ]

    def _list_provider_models(self) -> list[dict[str, Any]]:
        try:
            client = AIClient()
            return client.list_models()
        except Exception:
            return [{"id": "stub/default", "name": "stub/default"}]

    def _default_model_profile_text(self) -> str:
        return json.dumps(
            {
                "name": "Tencent HY3 Preview Free",
                "provider": "openrouter",
                "model_id": "tencent/hy3-preview:free",
                "profile_id": "openrouter/tencent/hy3-preview:free",
                "max_context": 32000,
                "supports_thinking": False,
                "thinking_level": None,
                "traits": ["free", "preview"],
                "strengths": ["general"],
            },
            ensure_ascii=False,
            indent=2,
        )

    def _schema_to_fields(self, schema: dict[str, Any]) -> list[dict[str, Any]]:
        properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
        required = set(schema.get("required", [])) if isinstance(schema, dict) else set()
        fields = []
        for key, value in properties.items():
            field_type = value.get("type", "string")
            ui_type = {"boolean": "toggle", "integer": "number", "number": "number"}.get(field_type, "text")
            if value.get("enum"):
                ui_type = "select"
            fields.append(
                {
                    "id": key,
                    "label": key,
                    "type": ui_type,
                    "required": key in required,
                    "default": value.get("default"),
                    "help": value.get("description", ""),
                    "options": [{"value": option, "label": str(option)} for option in value.get("enum", [])],
                }
            )
        return fields

    def _iso_to_ms(self, value: Any) -> int:
        if not value or not isinstance(value, str):
            return 0
        from datetime import datetime

        normalized = value.replace("Z", "+00:00")
        try:
            return int(datetime.fromisoformat(normalized).timestamp() * 1000)
        except ValueError:
            return 0

    def _deep_merge(self, base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
        result = deepcopy(base)
        for key, value in patch.items():
            if isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def _sanitize_settings_patch(self, patch: dict[str, Any]) -> dict[str, Any]:
        sanitized = deepcopy(patch)
        models = sanitized.get("models")
        if isinstance(models, dict):
            raw_key = models.pop("openrouter_api_key", None)
            if isinstance(raw_key, str) and raw_key.strip():
                result = set_provider_api_key(
                    "openrouter",
                    raw_key,
                    pack_root=self._pack_root,
                )
                models["openrouter_api_key_configured"] = bool(result.get("success"))
            else:
                models["openrouter_api_key_configured"] = provider_has_api_key(
                    "openrouter",
                    pack_root=self._pack_root,
                )
            models["openrouter_api_key"] = ""
        return sanitized

    def _refresh_derived_settings(self, values: dict[str, Any]) -> dict[str, Any]:
        refreshed = deepcopy(values)
        models = refreshed.setdefault("models", {})
        if isinstance(models, dict):
            models["openrouter_api_key"] = ""
            favorite_profiles = models.get("favorite_profiles")
            if isinstance(favorite_profiles, str):
                try:
                    parsed = json.loads(favorite_profiles)
                    favorite_profiles = parsed
                except json.JSONDecodeError:
                    favorite_profiles = [line.strip() for line in favorite_profiles.splitlines()]
            if not isinstance(favorite_profiles, list):
                preferred = str(models.get("preferred_model") or "stub/default").strip()
                favorite_profiles = [preferred] if preferred else ["stub/default"]
            normalized_favorites = []
            for item in favorite_profiles:
                profile_id = str(item or "").strip()
                if profile_id and profile_id not in normalized_favorites:
                    normalized_favorites.append(profile_id)
            models["favorite_profiles"] = normalized_favorites or ["stub/default"]
            levels = models.get("thinking_level_by_profile")
            if isinstance(levels, str):
                try:
                    levels = json.loads(levels)
                except json.JSONDecodeError:
                    levels = {}
            models["thinking_level_by_profile"] = levels if isinstance(levels, dict) else {}
            models["openrouter_api_key_configured"] = provider_has_api_key(
                "openrouter",
                pack_root=self._pack_root,
            )
        return refreshed
