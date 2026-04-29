from __future__ import annotations

import json
import base64
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
    @staticmethod
    def _jwt(payload):
        def encode(obj):
            raw = json.dumps(obj, separators=(",", ":")).encode("utf-8")
            return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

        return f"{encode({'alg': 'none'})}.{encode(payload)}."

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
                            {"id": "text", "component": "CustomText", "block_types": ["text"]},
                            {"id": "custom-renderer", "component": "Custom", "block_types": ["custom"]}
                        ],
                        "shell_renderers": [
                            {"id": "composer", "component": "CustomComposer", "regions": ["composer"]}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (pack_root / "user_data" / "shared" / "frontend_shell.json").write_text(
                json.dumps(
                    {
                        "shell_layout": {
                            "id": "compact",
                            "regions": [
                                {"id": "composer", "renderer": "composer", "order": 5, "enabled": True},
                                {"id": "history", "renderer": "history_board", "order": 20, "enabled": False},
                            ],
                        }
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
        renderers = {renderer["id"]: renderer for renderer in catalog["chat_rendering"]["renderers"]}
        shell_renderers = {renderer["id"]: renderer for renderer in catalog["shell"]["renderers"]}
        regions = {region["id"]: region for region in catalog["shell"]["layout"]["regions"]}
        part_ids = {part["id"] for part in catalog["parts"]}
        parts = {part["id"]: part for part in catalog["parts"]}
        binding_part_ids = {binding["part_id"] for binding in catalog["component_bindings"]}

        self.assertIn("web_search", sidebar_ids)
        self.assertIn("artifacts", sidebar_ids)
        self.assertIn("research-providers", sidebar_ids)
        self.assertIn("browser-computer", sidebar_ids)
        self.assertIn("scheduled-tasks", sidebar_ids)
        self.assertIn("collaboration", sidebar_ids)
        self.assertIn("share-export", sidebar_ids)
        self.assertIn("custom-widget", sidebar_ids)
        self.assertIn("custom", section_ids)
        self.assertIn("research", section_ids)
        self.assertIn("browser_computer", section_ids)
        self.assertIn("collaboration", section_ids)
        self.assertIn("share", section_ids)
        self.assertIn("custom-renderer", renderers)
        self.assertEqual(renderers["text"]["component"], "CustomText")
        self.assertEqual(shell_renderers["composer"]["component"], "CustomComposer")
        self.assertEqual(catalog["shell"]["layout"]["id"], "compact")
        self.assertEqual(regions["composer"]["order"], 5)
        self.assertFalse(regions["history"]["enabled"])
        self.assertIn("ai_chat", part_ids)
        self.assertIn("conversation_history", part_ids)
        self.assertIn("extension_sidebar", part_ids)
        self.assertIn("tool_timeline", parts["activity_preview"]["schema"]["properties"])
        self.assertIn("approvals", parts["activity_preview"]["schema"]["properties"])
        self.assertIn("audio", parts["activity_preview"]["schema"]["properties"])
        self.assertIn("messages", parts["ai_chat"]["schema"]["properties"])
        self.assertIn("ai_chat", binding_part_ids)
        self.assertEqual(catalog["app"]["icon"], "/static/assets/icons/defaultspack-icon.png")
        self.assertEqual(catalog["diagnostics"], [])

    def test_catalog_syncs_rumi_account_from_oauth_payload(self):
        from domain.frontend.registry import FrontendRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            rumi_root = Path(tmpdir) / "rumi_ai_1_10"
            pack_root = rumi_root / "ecosystem" / "defaultspack"
            token_path = rumi_root / "user_data" / "settings" / "oauth_tokens.json"
            token_path.parent.mkdir(parents=True, exist_ok=True)
            token_path.write_text(
                json.dumps(
                    {
                        "access_token": self._jwt(
                            {
                                "email": "user@example.test",
                                "user_metadata": {
                                    "full_name": "Rumi User",
                                    "avatar_url": "https://example.test/avatar.png",
                                },
                                "app_metadata": {"plan": "Pro Plan"},
                            }
                        )
                    }
                ),
                encoding="utf-8",
            )

            with patch("domain.frontend.registry.AIClient") as mock_client:
                mock_client.return_value.list_models.return_value = [{"id": "stub/default"}]
                catalog = FrontendRegistry(pack_root=pack_root).build_catalog()

        account = catalog["app"]["account"]
        self.assertEqual(account["display_name"], "Rumi User")
        self.assertEqual(account["email"], "user@example.test")
        self.assertEqual(account["plan_label"], "Pro Plan")
        self.assertEqual(account["avatar_url"], "https://example.test/avatar.png")
        self.assertEqual(account["source"], "rumi_oauth")

    def test_catalog_prefers_rumi_profile_for_account(self):
        from domain.frontend.registry import FrontendRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            rumi_root = Path(tmpdir) / "rumi_ai_1_10"
            pack_root = rumi_root / "ecosystem" / "defaultspack"
            profile_path = rumi_root / "user_data" / "settings" / "profile.json"
            profile_path.parent.mkdir(parents=True, exist_ok=True)
            profile_path.write_text(
                json.dumps(
                    {
                        "username": "Profile Name",
                        "language": "ja",
                        "icon": "https://example.test/profile.png",
                        "plan": "Team Plan",
                    }
                ),
                encoding="utf-8",
            )

            with patch("domain.frontend.registry.AIClient") as mock_client:
                mock_client.return_value.list_models.return_value = [{"id": "stub/default"}]
                catalog = FrontendRegistry(pack_root=pack_root).build_catalog()

        account = catalog["app"]["account"]
        self.assertEqual(account["display_name"], "Profile Name")
        self.assertEqual(account["plan_label"], "Team Plan")
        self.assertEqual(account["avatar_url"], "https://example.test/profile.png")
        self.assertEqual(account["source"], "rumi_profile")

    def test_malformed_frontend_shell_config_falls_back(self):
        from domain.frontend.registry import FrontendRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            pack_root = Path(tmpdir)
            shell_path = pack_root / "user_data" / "shared" / "frontend_shell.json"
            shell_path.parent.mkdir(parents=True, exist_ok=True)
            shell_path.write_text("{not json", encoding="utf-8")

            with patch("domain.frontend.registry.AIClient") as mock_client:
                mock_client.return_value.list_models.return_value = [{"id": "stub/default"}]
                catalog = FrontendRegistry(pack_root=pack_root).build_catalog()

        self.assertEqual(catalog["shell"]["layout"]["id"], "default_chat_shell")
        self.assertTrue(any(region["id"] == "chat_messages" for region in catalog["shell"]["layout"]["regions"]))
        self.assertTrue(any(item["code"] == "frontend_shell_invalid_json" for item in catalog["diagnostics"]))

    def test_catalog_reports_frontend_contract_diagnostics(self):
        from domain.frontend.registry import FrontendRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            pack_root = Path(tmpdir)
            ext_dir = pack_root / "user_data" / "shared" / "frontend_extensions"
            ext_dir.mkdir(parents=True, exist_ok=True)
            (ext_dir / "bad.ui.json").write_text(
                json.dumps(
                    {
                        "parts": [
                            {"id": "bad_part", "kind": "", "schema": []},
                        ],
                        "component_bindings": [
                            {"part_id": "missing_part", "component": "", "requires": "ai_client"},
                        ],
                        "shell_renderers": [
                            {"id": "bad_renderer", "component": "", "regions": "composer"},
                            {"id": "remote_renderer", "component": "Remote", "module": "https://example.com/remote.js"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (pack_root / "user_data" / "shared" / "frontend_shell.json").write_text(
                json.dumps(
                    {
                        "shell_layout": {
                            "regions": [
                                {"id": "bad_region", "part_id": "missing_part", "renderer": "missing_renderer", "order": "first"},
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )

            with patch("domain.frontend.registry.AIClient") as mock_client:
                mock_client.return_value.list_models.return_value = [{"id": "stub/default"}]
                catalog = FrontendRegistry(pack_root=pack_root).build_catalog()

        codes = {item["code"] for item in catalog["diagnostics"]}
        self.assertIn("part_missing_kind", codes)
        self.assertIn("part_invalid_schema", codes)
        self.assertIn("binding_unknown_part", codes)
        self.assertIn("binding_missing_component", codes)
        self.assertIn("binding_invalid_requires", codes)
        self.assertIn("shell_region_unknown_part", codes)
        self.assertIn("shell_region_unknown_renderer", codes)
        self.assertIn("shell_region_invalid_order", codes)
        self.assertIn("shell_renderer_missing_component", codes)
        self.assertIn("shell_renderer_invalid_regions", codes)
        self.assertIn("shell_renderer_untrusted_module", codes)
        self.assertIn("shell_renderer_missing_local_trust", codes)

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

    def test_update_settings_stores_openrouter_key_as_secret(self):
        from core_runtime.secrets_store import SecretsStore
        from domain.frontend.registry import FrontendRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            pack_root = Path(tmpdir)
            with patch("domain.frontend.registry.AIClient") as mock_client:
                mock_client.return_value.list_models.return_value = [{"id": "openrouter/tencent/hy3-preview:free"}]
                registry = FrontendRegistry(pack_root=pack_root)
                values = registry.update_settings({"models": {"openrouter_api_key": "or-secret"}})
                reloaded = registry.get_settings()["values"]

            settings_path = pack_root / "user_data" / "shared" / "frontend_settings.json"
            settings_text = settings_path.read_text(encoding="utf-8")
            store = SecretsStore(str(pack_root / "user_data" / "secrets"))
            has_secret = store.has_secret("OPENROUTER_API_KEY")

        self.assertTrue(values["models"]["openrouter_api_key_configured"])
        self.assertEqual(values["models"]["openrouter_api_key"], "")
        self.assertEqual(reloaded["models"]["openrouter_api_key"], "")
        self.assertNotIn("or-secret", settings_text)
        self.assertTrue(has_secret)

    def test_openrouter_key_status_is_derived_from_secret_store(self):
        from core_runtime.secrets_store import SecretsStore
        from domain.frontend.registry import FrontendRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            pack_root = Path(tmpdir)
            settings_path = pack_root / "user_data" / "shared" / "frontend_settings.json"
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            settings_path.write_text(
                json.dumps(
                    {
                        "models": {
                            "openrouter_api_key": "must-not-persist",
                            "openrouter_api_key_configured": False,
                        }
                    }
                ),
                encoding="utf-8",
            )
            store = SecretsStore(str(pack_root / "user_data" / "secrets"))
            store.set_secret("OPENROUTER_API_KEY", "or-secret", actor="test")

            with patch("domain.frontend.registry.AIClient") as mock_client:
                mock_client.return_value.list_models.return_value = [{"id": "openrouter/tencent/hy3-preview:free"}]
                values = FrontendRegistry(pack_root=pack_root).get_settings()["values"]

        self.assertEqual(values["models"]["openrouter_api_key"], "")
        self.assertTrue(values["models"]["openrouter_api_key_configured"])

    def test_fallback_http_routes_inject_method_for_block_handlers(self):
        from transport.registry import HttpRouteSpec, build_http_routes_from_specs

        class FakeServer:
            payload = None

            def _invoke_fallback_block(self, block_module, request_data, path_params, inject=None):
                self.payload = request_data
                return {"block_module": block_module, "path_params": path_params, "inject": inject}

        server = FakeServer()
        routes = build_http_routes_from_specs(
            server,
            [HttpRouteSpec("POST", "/api/ai/provider-key", block_module="blocks.ai.provider_key")],
        )
        result = routes[0][2]({"provider_id": "openrouter"}, {})

        self.assertEqual(result["block_module"], "blocks.ai.provider_key")
        self.assertEqual(server.payload["_method"], "POST")

    def test_fallback_http_routes_include_tools_list(self):
        from transport.registry import build_fallback_http_routes

        class FakeServer:
            def _invoke_fallback_block(self, block_module, request_data, path_params, inject=None):
                return {"block_module": block_module, "request_data": request_data}

            def _handle_health(self, request_data, path_params):
                return {}

            def _handle_context_info(self, request_data, path_params):
                return {}

            def _handle_static(self, request_data, path_params):
                return {}

            def _handle_static_file(self, request_data, path_params):
                return {}

        routes = build_fallback_http_routes(FakeServer())
        tools_route = next(
            handler
            for method, pattern, handler, _source, _inject in routes
            if method == "GET" and pattern.match("/api/tools")
        )
        result = tools_route({}, {})

        self.assertEqual(result["block_module"], "blocks.tool.list")
        self.assertEqual(result["request_data"]["_method"], "GET")

    def test_default_conversation_model_uses_openrouter_when_unconfigured(self):
        from domain.chat import store as chat_store

        self.assertEqual(
            chat_store._default_conversation_model(Path("/tmp/defaultspack-settings-does-not-exist.json")),
            "openrouter/tencent/hy3-preview:free",
        )

    def test_model_settings_are_editable_contracts(self):
        from domain.frontend.registry import FrontendRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            pack_root = Path(tmpdir)
            with patch("domain.frontend.registry.AIClient") as mock_client:
                mock_client.return_value.list_models.return_value = [{"id": "openrouter/tencent/hy3-preview:free"}]
                registry = FrontendRegistry(pack_root=pack_root)
                settings = registry.get_settings()
                values = registry.update_settings(
                    {
                        "models": {
                            "preferred_model": "openrouter/tencent/hy3-preview:free",
                            "model_profile": '{"name":"hy3","strengths":["general"]}',
                        }
                    }
                )

        model_fields = {
            field["id"]: field
            for section in settings["sections"]
            if section["id"] == "models"
            for field in section["fields"]
        }
        self.assertEqual(model_fields["preferred_model"]["type"], "text")
        self.assertEqual(model_fields["model_profile"]["type"], "textarea")
        self.assertEqual(values["models"]["preferred_model"], "openrouter/tencent/hy3-preview:free")
        self.assertIn("strengths", values["models"]["model_profile"])

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
