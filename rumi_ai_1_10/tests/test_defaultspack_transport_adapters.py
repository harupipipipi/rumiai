from __future__ import annotations

import sys
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


if __name__ == "__main__":
    unittest.main()
