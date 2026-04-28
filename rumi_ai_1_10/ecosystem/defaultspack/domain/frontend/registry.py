from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from domain.ai_client.client import AIClient
from domain.chat.store import ChatStore
from domain.dev.inspector import Inspector
from domain.extensions.runtime import get_extension_registry
from domain.tool.registry import ToolRegistry


class FrontendRegistry:
    """Registry for frontend catalog, settings, and chat preview metadata."""

    def __init__(self, pack_root: Path | None = None) -> None:
        self._pack_root = pack_root or Path(__file__).resolve().parents[2]
        self._extensions_dir = self._pack_root / "user_data" / "shared" / "frontend_extensions"
        self._settings_path = self._pack_root / "user_data" / "shared" / "frontend_settings.json"

    def build_catalog(self) -> dict[str, Any]:
        extensions = self._load_extensions()
        ui_surfaces = self._load_ui_surfaces()
        return {
            "app": self._app_metadata(ui_surfaces),
            "parts": self._parts(ui_surfaces, extensions),
            "component_bindings": self._component_bindings(ui_surfaces, extensions),
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
        }

    def get_settings(self) -> dict[str, Any]:
        ui_surfaces = self._load_ui_surfaces()
        return {
            "sections": self._settings_sections(ui_surfaces, self._load_extensions()),
            "values": self._read_settings(),
        }

    def update_settings(self, patch: dict[str, Any] | None) -> dict[str, Any]:
        current = self._read_settings()
        merged = self._deep_merge(current, patch or {})
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
        ]

    def _app_metadata(self, ui_surfaces: list[dict[str, Any]]) -> dict[str, Any]:
        app: dict[str, Any] = {
            "id": "defaultspack",
            "name": "Rumi Defaultspack",
            "icon": "/static/assets/icons/defaultspack-icon.png",
        }
        for surface in ui_surfaces:
            config = surface.get("config", {})
            if isinstance(config, dict) and isinstance(config.get("app"), dict):
                app = self._deep_merge(app, config["app"])
        return app

    def _parts(
        self,
        ui_surfaces: list[dict[str, Any]],
        extensions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        parts: list[dict[str, Any]] = [
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
            },
            {
                "id": "activity_preview",
                "kind": "preview",
                "label": "Activity Preview",
                "uses": ["chat", "dev", "tool", "knowledge", "memory", "media"],
                "contracts": {
                    "preview": "/api/ui/conversations/{conversation_id}/preview",
                },
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
                "description": "現在検出されている provider と model catalog の参照。",
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
                        "type": "select",
                        "default": "stub/default",
                        "options": self._model_options(),
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

        return renderers

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
                extensions.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        return extensions

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
        return values

    def _default_settings(self) -> dict[str, Any]:
        return {
            "general": {"composer_placeholder": "メッセージを入力...", "show_activity_in_messages": True},
            "preview": {"auto_open": False, "default_mode": "auto", "max_items": 12},
            "chat_rendering": {"render_markdown": True, "show_widgets": True, "unknown_block_strategy": "json"},
            "models": {"detected_provider_count": len(self._list_provider_models()), "preferred_model": "stub/default"},
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
