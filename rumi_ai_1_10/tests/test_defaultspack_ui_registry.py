from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


class TestDefaultspackUiRegistry(unittest.TestCase):
    def test_catalog_merges_tool_registry_and_extension_manifest(self):
        from domain.frontend.registry import FrontendRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            pack_root = Path(tmpdir)
            ext_dir = pack_root / "user_data" / "shared" / "frontend_extensions"
            ext_dir.mkdir(parents=True, exist_ok=True)
            (ext_dir / "extra.ui.json").write_text(
                json.dumps(
                    {
                        "sidebar_items": [
                            {
                                "id": "custom-widget",
                                "label": "Custom Widget",
                                "category": "widget",
                            }
                        ],
                        "settings_sections": [
                            {
                                "id": "custom",
                                "label": "Custom",
                                "fields": [
                                    {"id": "enabled", "label": "Enabled", "type": "toggle", "default": True}
                                ],
                            }
                        ],
                        "chat_renderers": [
                            {"id": "custom-renderer", "component": "Custom", "block_types": ["custom"]}
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with patch("domain.frontend.registry.AIClient") as mock_client:
                mock_client.return_value.list_models.return_value = [{"id": "stub/default"}]
                registry = FrontendRegistry(pack_root=pack_root)
                catalog = registry.build_catalog()

        sidebar_ids = {item["id"] for item in catalog["sidebar"]["items"]}
        section_ids = {section["id"] for section in catalog["settings"]["sections"]}
        renderer_ids = {renderer["id"] for renderer in catalog["chat_rendering"]["renderers"]}
        part_ids = {part["id"] for part in catalog["parts"]}
        binding_part_ids = {binding["part_id"] for binding in catalog["component_bindings"]}

        self.assertIn("web_search", sidebar_ids)
        self.assertIn("custom-widget", sidebar_ids)
        self.assertIn("custom", section_ids)
        self.assertIn("custom-renderer", renderer_ids)
        self.assertIn("ai_chat", part_ids)
        self.assertIn("ai_chat", binding_part_ids)
        self.assertEqual(catalog["app"]["icon"], "/static/assets/icons/defaultspack-icon.png")

    def test_update_settings_persists_values(self):
        from domain.frontend.registry import FrontendRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            pack_root = Path(tmpdir)
            with patch("domain.frontend.registry.AIClient") as mock_client:
                mock_client.return_value.list_models.return_value = [{"id": "stub/default"}]
                registry = FrontendRegistry(pack_root=pack_root)
                values = registry.update_settings({"preview": {"auto_open": True, "max_items": 5}})
                reloaded = registry.get_settings()["values"]

        self.assertTrue(values["preview"]["auto_open"])
        self.assertEqual(values["preview"]["max_items"], 5)
        self.assertTrue(reloaded["preview"]["auto_open"])
        self.assertEqual(reloaded["preview"]["max_items"], 5)

    def test_conversation_preview_uses_inspector_and_message_widgets(self):
        from domain.chat.store import ChatStore
        from domain.dev.inspector import Inspector
        from domain.frontend.registry import FrontendRegistry

        store = ChatStore()
        store._conversations = {}
        inspector = Inspector()
        inspector.clear()

        conversation = store.create_conversation()
        store.add_message(
            conversation["id"],
            {
                "role": "assistant",
                "content": [{"type": "code", "filename": "demo.py", "language": "python", "text": "print('hi')"}],
                "widget": {"type": "indicator", "label": "Running"},
            },
        )
        inspector.log_request(
            request_id="req-1",
            conversation_id=conversation["id"],
            tools_called=["web_search"],
            context_info={
                "knowledge_results": [{"content": "Knowledge body", "metadata": {"title": "Knowledge"}}],
                "memory_results": [{"content": "Memory body", "score": 0.8}],
            },
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("domain.frontend.registry.AIClient") as mock_client:
                mock_client.return_value.list_models.return_value = [{"id": "stub/default"}]
                registry = FrontendRegistry(pack_root=Path(tmpdir))
                preview = registry.build_conversation_preview(conversation["id"])

        preview_ids = {item["id"] for item in preview["previews"]}
        self.assertTrue(any(item.startswith("tool-web_search") for item in preview_ids))
        self.assertTrue(any(item.startswith("widget-") for item in preview_ids))
        self.assertTrue(any(item.startswith("code-") for item in preview_ids))

    def test_ui_routes_registered_for_kernel_and_fallback(self):
        from blocks.ui.setup import run as setup_ui_routes
        from transport.registry import build_fallback_http_routes

        class FakeInterfaceRegistry:
            def __init__(self):
                self.routes = []

            def register(self, key, value, meta=None):
                if key == "io.http.route":
                    self.routes.append(value)

        registry = FakeInterfaceRegistry()
        result = setup_ui_routes({"interface_registry": registry})
        registered_patterns = {route["pattern"] for route in registry.routes}

        class FakeServer:
            def _invoke_fallback_block(self, module_name, request_data, path_params, inject=None):
                return {"module_name": module_name}

            def _handle_health(self, request_data, path_params):
                return {}

            def _handle_context_info(self, request_data, path_params):
                return {}

            def _handle_static(self, request_data, path_params):
                return {}

            def _handle_static_file(self, request_data, path_params):
                return {}

        fallback_patterns = {compiled.pattern for _, compiled, _, _, _ in build_fallback_http_routes(FakeServer())}

        self.assertEqual(result["status"], "ok")
        self.assertIn("/api/ui/catalog", registered_patterns)
        self.assertIn("/api/ui/settings", registered_patterns)
        self.assertIn("/api/ui/conversations/{id}/preview", registered_patterns)
        self.assertTrue(any("api/ui/catalog" in pattern for pattern in fallback_patterns))
        self.assertTrue(any("api/ui/conversations" in pattern for pattern in fallback_patterns))

    def test_static_asset_serving_is_binary_and_assets_scoped(self):
        from transport.http import DefaultsHttpServer

        with tempfile.TemporaryDirectory() as tmpdir:
            pack_root = Path(tmpdir)
            (pack_root / "assets" / "icons").mkdir(parents=True)
            (pack_root / "ui").mkdir()
            (pack_root / "assets" / "icons" / "icon.png").write_bytes(b"\x89PNG\r\n")
            (pack_root / "ecosystem.json").write_text("{}", encoding="utf-8")

            server = DefaultsHttpServer(facade=None)
            original_file = __import__("transport.http", fromlist=["__file__"]).__file__
            try:
                import transport.http as http_module

                http_module.__file__ = str(pack_root / "transport" / "http.py")
                asset = server._handle_static_file({}, {"path": "assets/icons/icon.png"})
                hidden = server._handle_static_file({}, {"path": "ecosystem.json"})
            finally:
                http_module.__file__ = original_file

        self.assertEqual(asset["content_type"], "image/png")
        self.assertEqual(asset["body"], b"\x89PNG\r\n")
        self.assertEqual(hidden["status"], "error")


if __name__ == "__main__":
    unittest.main()
