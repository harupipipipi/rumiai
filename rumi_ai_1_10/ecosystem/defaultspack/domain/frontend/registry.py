from __future__ import annotations

import base64
import json
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.parse import quote

from domain.ai_client.client import AIClient
from domain.ai_client.api_key_store import provider_key_status, set_provider_api_key
from domain.ai_client.model_runtime_settings import ModelRuntimeSettingsService
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
            "name": "RumiDP",
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
                "uses": ["chat", "dev", "tool", "context", "media", "artifact", "extension"],
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
                "uses": ["tool", "widget", "frontend", "artifact", "extension"],
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
            ui = dict(tool.get("ui", {})) if isinstance(tool.get("ui"), dict) else {}
            risk = str(tool.get("risk") or tool.get("metadata", {}).get("risk") or "low").strip().lower()
            tags = [str(tag) for tag in tool.get("tags", []) if str(tag)]
            if risk == "high" and "danger" not in tags:
                tags.append("danger")
            items.append(
                {
                    "id": tool.get("tool_id", tool.get("name", "tool")),
                    "label": tool.get("name", tool.get("tool_id", "tool")),
                    "category": "tool",
                    "description": tool.get("summary", ""),
                    "badge": "Dynamic" if execution_type == "dynamic" else None,
                    "tags": tags,
                    "risk": risk,
                    "ui": ui,
                    "origin": {"kind": "tool_registry", "path": "domain/tool/registry.py"},
                    "panel": {
                        "kind": "tool_settings",
                        "title": tool.get("name", tool.get("tool_id", "tool")),
                        "fields": self._tool_settings_fields(ui),
                        "notes": [
                            "Tool call arguments stay in ToolRegistry schema and are not shown as settings.",
                            self._tool_schema_summary(schema),
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
                    "description": "defaultspack core capability catalog.",
                    "tags": ["agent", "capability", "local-first"],
                    "origin": {"kind": "builtin", "path": "capabilities/"},
                    "panel": {
                        "kind": "info",
                        "title": "Agent Service Capabilities",
                        "notes": [
                            "The core registry exposes capability contracts.",
                            "Concrete UI entries are supplied by frontend extension packs.",
                        ],
                    },
                }
            ]
        )

        items.extend(self._config_list(ui_surfaces, "sidebar_items"))
        items.extend(self._hydrate_sidebar_items(self._config_list(extensions, "sidebar_items")))

        return sorted(self._dedupe_by_key(items, "id"), key=self._sidebar_item_sort_key)

    @staticmethod
    def _sidebar_item_sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
        category_order = {
            "tool": 0,
            "widget": 1,
            "capability": 2,
            "integration": 3,
            "system": 4,
        }
        tool_group_order = {
            "browser": 0,
            "computer": 1,
            "coding/files/read": 10,
            "coding/files/write": 11,
            "coding/github/status": 20,
            "coding/github/commit": 21,
            "coding/terminal/exec": 30,
            "build": 40,
            "terminal": 50,
            "research": 60,
            "planning": 70,
            "agent": 80,
            "manage": 90,
            "operate": 100,
            "other": 999,
        }
        category = str(item.get("category", "system"))
        ui = item.get("ui")
        ui = ui if isinstance(ui, dict) else {}
        group_id = str(ui.get("group_id") or "")
        group_root = group_id.split("/", 1)[0] if group_id else ""
        group_rank = tool_group_order.get(group_id, tool_group_order.get(group_root, 500))
        label = str(item.get("label") or item.get("id") or "").casefold()
        item_id = str(item.get("id") or "").casefold()
        return (category_order.get(category, 99), group_rank, group_id.casefold(), label, item_id)

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
                    {"id": "show_widgets", "label": "Render Widgets", "type": "toggle", "default": True},
                    {
                        "id": "unknown_block_strategy",
                        "label": "Unknown Block Strategy",
                        "type": "select",
                        "default": "hidden",
                        "options": [
                            {"value": "hidden", "label": "Hide"},
                            {"value": "text", "label": "Plain Text"},
                            {"value": "json", "label": "JSON Fallback"},
                        ],
                    },
                ],
            },
            {
                "id": "models",
                "label": "Models",
                "description": "会話で使うモデルと thinking 設定。",
                "fields": [
                    {
                        "id": "preferred_model",
                        "label": "Preferred Model",
                        "type": "select",
                        "default": "stub/default",
                        "options": self._model_options(),
                        "help": "新しい会話と composer の既定モデルです。",
                    },
                    {
                        "id": "thinking_level",
                        "label": "Thinking Level",
                        "type": "select",
                        "default": "medium",
                        "options": [
                            {"value": "none", "label": "Off"},
                            {"value": "low", "label": "Low"},
                            {"value": "medium", "label": "Medium"},
                            {"value": "high", "label": "High"},
                            {"value": "xhigh", "label": "Extra High"},
                        ],
                        "help": "Rumi は none/low/medium/high/xhigh を送り、各 provider が対応する API パラメータへ変換します。Gemini/Gemma では未対応の値を自動で近い値へ落とします。",
                    },
                    {
                        "id": "favorite_profiles",
                        "label": "Composer Model Pins",
                        "type": "textarea",
                        "default": "stub/default",
                        "help": "高度設定: composer に優先表示する profile_id。通常は Preferred Model だけで十分です。",
                        "advanced": True,
                    },
                    {
                        "id": "thinking_level_by_profile",
                        "label": "Per-profile Thinking Map",
                        "type": "textarea",
                        "default": '{"stub/default":"medium"}',
                        "help": "高度設定: profile_id ごとの上書き。通常は Thinking Level を使います。",
                        "advanced": True,
                    },
                ],
            },
            {
                "id": "apis",
                "label": "APIs",
                "description": "名前付き API key と、モデルごとの API 優先順位。",
                "fields": [
                    {
                        "id": "api_keys",
                        "label": "API Keys",
                        "type": "api_keys",
                        "default": [],
                        "help": "provider と名前を付けて複数の API key を保存できます。値は再表示されません。",
                    },
                    {
                        "id": "model_api_routes",
                        "label": "Model API Priority",
                        "type": "textarea",
                        "default": "",
                        "help": "1行に model: provider/api-name を優先順で書きます。例: google/gemini-2.5-pro: google/main, google/backup",
                    },
                ],
            },
            {
                "id": "commands",
                "label": "Commands",
                "description": "Slash command visibility and command palette behavior.",
                "fields": [
                    {
                        "id": "show_advanced_commands",
                        "label": "Show Advanced Commands",
                        "type": "toggle",
                        "default": False,
                        "help": "Advanced slash commandsを候補に含めます。hidden command は直接入力か将来の管理UI向けです。",
                    },
                ],
            },
            {
                "id": "tools",
                "label": "Tools",
                "description": "Tool composer defaults and selection behavior.",
                "fields": [
                    {
                        "id": "default_target",
                        "label": "Default Target",
                        "type": "text",
                        "default": "",
                        "help": "Backcompat value for tool UIs that still read a shared default_target.",
                        "advanced": True,
                    },
                    {
                        "id": "keep_selected_tools_after_send",
                        "label": "Keep Selected Tools",
                        "type": "toggle",
                        "default": False,
                        "help": "Keep composer tool selections after a message is sent.",
                    },
                ],
            },
            {
                "id": "debug",
                "label": "Debug",
                "description": "モデル呼び出しとcomputer use調査用のログ設定。",
                "fields": [
                    {
                        "id": "ai_request_logging",
                        "label": "AI Request Logs",
                        "type": "toggle",
                        "default": False,
                        "help": "AIに渡すmessages/tools/paramsと添付画像を会話workspace/debug/ai_requestsへ保存します。",
                    },
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
                "path": "packs/frontend_extensions/*.ui.json or user_data/shared/frontend_extensions/*.ui.json",
                "description": "Right sidebar entries and their panel metadata.",
            },
            {
                "id": "settings_sections",
                "path": "packs/frontend_extensions/*.ui.json or user_data/shared/frontend_extensions/*.ui.json",
                "description": "Settings modal sections / fields. Saved into frontend_settings.json.",
            },
            {
                "id": "chat_renderers",
                "path": "packs/frontend_extensions/*.ui.json or user_data/shared/frontend_extensions/*.ui.json",
                "description": "Metadata describing custom block/widget renderers.",
            },
            {
                "id": "composer.inline",
                "path": "packs/frontend_extensions/*.ui.json or user_data/shared/frontend_extensions/*.ui.json config.composer.inline",
                "description": "Small action buttons rendered inside the composer control row.",
            },
            {
                "id": "composer.below",
                "path": "packs/frontend_extensions/*.ui.json or user_data/shared/frontend_extensions/*.ui.json config.composer.below",
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
                "path": "extensions/ui/*/manifest.json config.shell_renderers or packs/frontend_extensions/*.ui.json",
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
        for index, log in enumerate(message.get("tool_logs") or []):
            if isinstance(log, dict):
                previews.extend(self._preview_from_tool_log(message, log, index))
        return previews

    def _preview_from_tool_log(self, message: dict[str, Any], log: dict[str, Any], index: int) -> list[dict[str, Any]]:
        timestamp = int(message.get("created_at", 0)) - 200 - index
        tool_name = str(log.get("tool_name") or "tool")
        arguments = log.get("arguments") if isinstance(log.get("arguments"), dict) else {}
        result = log.get("result")
        input_text = self._preview_text(arguments, 180)
        result_text = self._preview_text(result, 480)
        status = "failed" if isinstance(result, dict) and result.get("status") == "error" else "completed"
        lines = [
            f"tool: {tool_name}",
            f"status: {status}",
        ]
        if input_text:
            lines.append(f"input: {input_text}")
        if result_text:
            lines.append(f"result: {result_text}")
        previews = [{
            "id": f"tool-log-{message.get('id')}-{index}",
            "toolStepId": tool_name,
            "timestamp": timestamp,
            "data": {
                "type": "file",
                "filename": f"{tool_name}.tool",
                "size": status,
                "content": "\n".join(lines),
            },
        }]
        conversation_id = str(message.get("conversation_id") or "")
        for artifact_index, path in enumerate(self._artifact_paths_from_value(result)):
            name = Path(path).name or "artifact"
            url = "/api/chat/conversations/{}/artifact-file?path={}".format(
                quote(conversation_id, safe=""),
                quote(path, safe=""),
            )
            if self._is_image_path(path):
                previews.append(
                    {
                        "id": f"tool-log-artifact-{message.get('id')}-{index}-{artifact_index}",
                        "toolStepId": tool_name,
                        "timestamp": timestamp + artifact_index + 0.1,
                        "data": {
                            "type": "image",
                            "url": url,
                            "alt": name,
                            "path": path,
                        },
                    }
                )
            else:
                previews.append(
                    {
                        "id": f"tool-log-artifact-{message.get('id')}-{index}-{artifact_index}",
                        "toolStepId": tool_name,
                        "timestamp": timestamp + artifact_index + 0.1,
                        "data": {
                            "type": "file",
                            "filename": name,
                            "size": "tool artifact",
                            "path": path,
                            "url": url,
                            "downloadName": name,
                            "content": f"artifact: {path}",
                        },
                    }
                )
        return previews

    def _artifact_paths_from_value(self, value: Any, seen: set[str] | None = None) -> list[str]:
        seen = seen or set()
        paths: list[str] = []
        if isinstance(value, dict):
            preferred = ""
            for key in ("model_image_path", "screenshot_path", "path"):
                item = value.get(key)
                if isinstance(item, str) and item.strip():
                    preferred = item.strip()
                    break
            if preferred and preferred not in seen:
                seen.add(preferred)
                paths.append(preferred)
            for key, item in value.items():
                if key in {"path", "screenshot_path", "model_image_path", "data_url", "dataUrl"}:
                    continue
                paths.extend(self._artifact_paths_from_value(item, seen))
        elif isinstance(value, list):
            for item in value:
                paths.extend(self._artifact_paths_from_value(item, seen))
        return paths

    @staticmethod
    def _is_image_path(path: str) -> bool:
        return Path(path).suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}

    def _preview_text(self, value: Any, limit: int) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            text = value
        elif isinstance(value, (int, float, bool)):
            text = str(value)
        else:
            text = json.dumps(value, ensure_ascii=False, sort_keys=True)
        text = " ".join(text.split())
        return text if len(text) <= limit else f"{text[:limit - 1]}…"

    def _load_ui_surfaces(self) -> list[dict[str, Any]]:
        try:
            surfaces = get_extension_registry().ui_surfaces().list(enabled_only=True)
        except Exception:
            surfaces = []
        return [surface for surface in surfaces if isinstance(surface, dict)]

    def _load_extensions(self) -> list[dict[str, Any]]:
        extensions = []
        for path in self._frontend_extension_paths():
            try:
                extension = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(extension, dict):
                    extension["_source"] = str(path)
                    extension["source_pack_id"] = self._source_pack_id(path)
                    extensions.append(extension)
                else:
                    self._add_diagnostic("warning", "frontend_extension_not_object", f"{path} must contain a JSON object.", str(path))
            except (OSError, json.JSONDecodeError) as exc:
                self._add_diagnostic("warning", "frontend_extension_invalid_json", str(exc), str(path))
                continue
        return extensions

    def _frontend_extension_paths(self) -> list[Path]:
        paths: list[Path] = []
        seen: set[Path] = set()
        for directory in self._frontend_extension_dirs():
            if not directory.exists():
                continue
            for path in sorted(directory.glob("*.ui.json")):
                resolved = path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                paths.append(path)
        return paths

    def _frontend_extension_dirs(self) -> list[Path]:
        dirs: list[Path] = []
        ecosystem_root = self._ecosystem_root()
        if ecosystem_root.exists():
            for pack_root in sorted(ecosystem_root.iterdir()):
                if not pack_root.is_dir() or not (pack_root / "ecosystem.json").exists():
                    continue
                dirs.append(pack_root / "frontend_extensions")
        dirs.append(self._extensions_dir)
        return dirs

    def _ecosystem_root(self) -> Path:
        if (self._pack_root / "ecosystem.json").exists() and self._pack_root.parent.name == "ecosystem":
            return self._pack_root.parent
        return Path(__file__).resolve().parents[3]

    def _source_pack_id(self, path: Path) -> str:
        for parent in path.parents:
            if (parent / "ecosystem.json").exists():
                return parent.name
        return "user_data"

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

    def _hydrate_sidebar_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        hydrated: list[dict[str, Any]] = []
        for item in items:
            item = deepcopy(item)
            panel = item.get("panel")
            if isinstance(panel, dict) and panel.get("kind") == "models" and "models" not in panel:
                panel["models"] = self._list_provider_models()
            hydrated.append(item)
        return hydrated

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
            "chat_rendering": {"show_widgets": True, "unknown_block_strategy": "hidden"},
            "models": {
                **ModelRuntimeSettingsService(self._pack_root).default_model_settings(),
            },
            "commands": {
                "show_advanced_commands": False,
            },
            "tools": {
                "default_target": "",
                "keep_selected_tools_after_send": False,
            },
            "debug": {
                "ai_request_logging": False,
            },
            "sidebar": {
                "pinned_item_ids": [],
                "starred_item_ids": [],
                "custom_tool_tags": {},
            },
            "apis": {
                "api_keys": [],
                "model_api_routes": "",
            },
        }

    def _model_options(self) -> list[dict[str, str]]:
        profiles = self._selectable_model_profiles()
        return [
            {
                "value": profile["profile_id"],
                "label": self._model_option_label(profile),
            }
            for profile in profiles
        ] or [{"value": "stub/default", "label": "Stub Default"}]

    def _selectable_model_profiles(self) -> list[dict[str, Any]]:
        try:
            from ecosystem.defaultspack.backend.ai_client.provider_catalog import list_profile_catalog
        except ModuleNotFoundError:
            try:
                from backend.ai_client.provider_catalog import list_profile_catalog
            except ModuleNotFoundError:
                list_profile_catalog = None

        if list_profile_catalog is not None:
            profiles = list_profile_catalog()
        else:
            profiles = [
                {
                    "profile_id": model["id"],
                    "display_name": model.get("name") or model["id"],
                    "provider_id": model.get("provider_id") or model.get("provider"),
                    "model_id": model.get("model_id") or str(model.get("id", "")).split("/", 1)[-1],
                    "type": model.get("type", "chat"),
                    "availability": model.get("availability", {}),
                }
                for model in self._list_provider_models()
            ]

        filtered = [profile for profile in profiles if self._is_user_selectable_profile(profile)]
        filtered.sort(key=self._model_profile_sort_key)
        return filtered

    def _is_user_selectable_profile(self, profile: dict[str, Any]) -> bool:
        provider_id = str(profile.get("provider_id") or profile.get("provider") or "").strip()
        model_id = str(profile.get("model_id") or "").strip()
        model_type = str(profile.get("type") or "chat").strip().lower()
        availability = profile.get("availability") if isinstance(profile.get("availability"), dict) else {}

        if model_type and model_type != "chat":
            return False
        if provider_id == "rumi":
            return False
        if provider_id == "stub":
            return model_id == "default"
        if profile.get("local") or availability.get("local") or availability.get("offline"):
            return True
        if self._is_unconfigured_direct_cloud_profile(provider_id, availability):
            return True
        return bool(
            availability.get("configured")
            or availability.get("active")
            or availability.get("status") in {"configured", "active"}
        )

    def _is_unconfigured_direct_cloud_profile(
        self,
        provider_id: str,
        availability: dict[str, Any],
    ) -> bool:
        """Expose direct cloud models as selectable setup targets without enabling runtime calls."""
        if provider_id not in {"openai", "anthropic", "google", "genspark"}:
            return False
        if availability.get("configured") or availability.get("active"):
            return False
        if availability.get("catalog_only"):
            return False
        return bool(availability.get("supports_invoke"))

    def _model_profile_sort_key(self, profile: dict[str, Any]) -> tuple[int, int, str]:
        model_id = str(profile.get("model_id") or "").strip()
        availability = profile.get("availability") if isinstance(profile.get("availability"), dict) else {}
        is_default = str(profile.get("profile_id") or "") == "stub/default"
        is_local = bool(profile.get("local") or availability.get("local") or availability.get("offline"))
        is_configured = bool(
            availability.get("configured")
            or availability.get("active")
            or str(availability.get("status", "")).lower() in {"configured", "active"}
        )
        provider_order = 0 if is_default else (1 if is_local else (2 if is_configured else 9))
        model_order = 0 if model_id == "default" else 20
        return (provider_order, model_order, str(profile.get("display_name") or profile.get("profile_id") or ""))

    def _model_option_label(self, profile: dict[str, Any]) -> str:
        provider = str(
            profile.get("provider_display_name")
            or profile.get("provider_id")
            or profile.get("provider")
            or ""
        ).strip()
        name = str(profile.get("display_name") or profile.get("profile_id") or "").strip()
        availability = profile.get("availability") if isinstance(profile.get("availability"), dict) else {}
        provider_id = str(profile.get("provider_id") or profile.get("provider") or "").strip()
        requires_key = (
            not (profile.get("local") or availability.get("local") or availability.get("offline"))
            and provider_id not in {"stub", "rumi"}
            and not availability.get("configured")
        )
        suffix = " - API key required" if requires_key else ""
        return f"{provider} / {name}{suffix}" if provider else f"{name}{suffix}"

    def _list_provider_models(self) -> list[dict[str, Any]]:
        try:
            client = AIClient()
            return client.list_models()
        except Exception:
            return [{"id": "stub/default", "name": "stub/default"}]

    def _tool_settings_fields(self, ui: dict[str, Any]) -> list[dict[str, Any]]:
        fields = ui.get("settings_fields", [])
        if not isinstance(fields, list):
            return []
        return [field for field in fields if isinstance(field, dict)]

    def _tool_schema_summary(self, schema: dict[str, Any]) -> str:
        properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
        if not isinstance(properties, dict) or not properties:
            return "This tool does not declare runtime arguments."
        names = ", ".join(str(name) for name in properties.keys())
        return f"Runtime arguments: {names}."

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
        apis = sanitized.get("apis")
        if isinstance(apis, dict):
            api_key_patch = apis.pop("api_keys", None)
            if isinstance(api_key_patch, dict) and api_key_patch.get("action") == "upsert":
                provider_id = str(api_key_patch.get("provider_id") or "").strip()
                name = str(api_key_patch.get("name") or api_key_patch.get("api_id") or "").strip()
                value = str(api_key_patch.get("value") or "")
                if provider_id and name and value.strip():
                    set_provider_api_key(
                        provider_id,
                        value,
                        pack_root=self._pack_root,
                        api_id=name,
                        name=name,
                    )
            apis["api_keys"] = []
        models = sanitized.get("models")
        if isinstance(models, dict):
            sanitized["models"] = ModelRuntimeSettingsService(
                self._pack_root
            ).sanitize_models_patch(models)
        return sanitized

    def _refresh_derived_settings(self, values: dict[str, Any]) -> dict[str, Any]:
        refreshed = deepcopy(values)
        debug = refreshed.setdefault("debug", {})
        if not isinstance(debug, dict):
            debug = {}
            refreshed["debug"] = debug
        debug.setdefault("ai_request_logging", False)

        tools = refreshed.setdefault("tools", {})
        if not isinstance(tools, dict):
            tools = {}
            refreshed["tools"] = tools
        tools.setdefault("keep_selected_tools_after_send", False)
        legacy_default_target = self._legacy_default_target(refreshed)
        if "default_target" not in tools or (not str(tools.get("default_target") or "").strip() and legacy_default_target):
            tools["default_target"] = legacy_default_target

        apis = refreshed.setdefault("apis", {})
        if isinstance(apis, dict):
            apis["api_keys"] = provider_key_status(pack_root=self._pack_root)
            routes = apis.get("model_api_routes")
            if isinstance(routes, list):
                routes = "\n".join(str(item).strip() for item in routes if str(item).strip())
            apis["model_api_routes"] = str(routes or "").strip() + ("\n" if str(routes or "").strip() else "")
        models = refreshed.setdefault("models", {})
        if isinstance(models, dict):
            refreshed["models"] = ModelRuntimeSettingsService(
                self._pack_root
            ).refresh_models_settings(models)
        return refreshed

    @staticmethod
    def _legacy_default_target(values: dict[str, Any]) -> str:
        for container_key in ("debug", "browser", "browser_use"):
            container = values.get(container_key)
            if not isinstance(container, dict):
                continue
            value = container.get("default_target")
            if value is not None:
                return str(value)
        value = values.get("default_target")
        return str(value) if value is not None else ""
