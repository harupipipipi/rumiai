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

        self.assertIn("web_search", sidebar_ids)
        self.assertIn("custom-widget", sidebar_ids)
        self.assertIn("custom", section_ids)
        self.assertIn("custom-renderer", renderer_ids)

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


if __name__ == "__main__":
    unittest.main()
