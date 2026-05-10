from __future__ import annotations

import importlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestDefaultspackTransportAdapters(unittest.TestCase):
    def test_http_transport_does_not_direct_import_block_run(self):
        transport_path = (
            Path(__file__).resolve().parent.parent
            / "ecosystem"
            / "defaultspack"
            / "transport"
            / "http.py"
        )
        source = transport_path.read_text(encoding="utf-8")
        self.assertNotRegex(source, r"from blocks\.[\w\.]+ import run")
        self.assertIn("invoke_block(", source)

    def test_cli_transport_does_not_direct_import_block_run(self):
        transport_path = (
            Path(__file__).resolve().parent.parent
            / "ecosystem"
            / "defaultspack"
            / "transport"
            / "cli.py"
        )
        source = transport_path.read_text(encoding="utf-8")
        self.assertNotRegex(source, r"from blocks\.[\w\.]+ import run")
        self.assertIn("invoke_block(", source)

    def test_block_adapter_recovers_from_foreign_blocks_package(self):
        repo_root = Path(__file__).resolve().parent.parent
        pack_root = repo_root / "ecosystem" / "defaultspack"
        original_path = list(sys.path)
        original_modules = dict(sys.modules)

        with tempfile.TemporaryDirectory() as temp_dir:
            fake_root = Path(temp_dir)
            fake_blocks = fake_root / "blocks"
            fake_blocks.mkdir()
            (fake_blocks / "__init__.py").write_text("# foreign blocks package\n", encoding="utf-8")
            sys.path.insert(0, str(fake_root))
            importlib.import_module("blocks")

            try:
                sys.path.insert(0, str(pack_root))
                from bridge.block_adapter import invoke_block

                result = invoke_block("blocks.tool.list", {}, {})
                self.assertEqual(result.get("status"), "ok")
                active_blocks = sys.modules.get("blocks")
                self.assertIsNotNone(active_blocks)
                active_file = getattr(active_blocks, "__file__", "")
                self.assertIn(str(pack_root), active_file)
            finally:
                sys.path[:] = original_path
                for loaded_name in list(sys.modules):
                    if loaded_name not in original_modules:
                        sys.modules.pop(loaded_name, None)
                sys.modules.update(original_modules)

    def test_chat_send_infers_computer_tools_from_compute_use_typo(self):
        repo_root = Path(__file__).resolve().parent.parent
        pack_root = repo_root / "ecosystem" / "defaultspack"
        original_path = list(sys.path)
        try:
            sys.path.insert(0, str(pack_root))
            chat_send = importlib.import_module("blocks.chat.send")
            inferred = chat_send._infer_requested_tools_from_message(
                "gemma4の高にcompute useを指示して、VivaldiでLINEを操作して"
            )
            self.assertIn("computer_use", inferred)
            self.assertIn("browser_computer", inferred)
            updated = chat_send._with_inferred_tools({"tools": []}, inferred)
            self.assertEqual(updated["tools"], ["computer_use", "browser_computer"])
        finally:
            sys.path[:] = original_path


if __name__ == "__main__":
    unittest.main()
