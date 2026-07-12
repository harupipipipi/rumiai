from __future__ import annotations

import json
import unittest
from pathlib import Path

from domain.ai_client.providers.google_provider import GoogleProvider


PACK_ROOT = Path(__file__).resolve().parents[1]


def _array_paths_missing_items(node, path="$"):
    missing = []
    if isinstance(node, dict):
        if node.get("type") == "array" and "items" not in node:
            missing.append(path)
        for key, value in node.items():
            missing.extend(_array_paths_missing_items(value, f"{path}.{key}"))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            missing.extend(_array_paths_missing_items(value, f"{path}[{index}]"))
    return missing


class GoogleSchemaManifestTests(unittest.TestCase):
    def test_native_schema_normalizes_nullable_and_array_items(self):
        schema = {
            "type": "object",
            "properties": {
                "conversation": {"type": ["object", "null"]},
                "rows": {"type": "array"},
            },
        }

        native = GoogleProvider._native_schema(schema)

        self.assertEqual(native["properties"]["conversation"]["type"], "object")
        self.assertTrue(native["properties"]["conversation"]["nullable"])
        self.assertEqual(native["properties"]["rows"]["type"], "array")
        self.assertEqual(
            native["properties"]["rows"]["items"],
            {"type": "object", "properties": {}, "required": []},
        )

    def test_tool_and_ui_manifests_define_items_for_arrays(self):
        manifest_paths = sorted((PACK_ROOT / "tools").glob("*/manifest.json"))
        manifest_paths.extend(sorted((PACK_ROOT / "extensions" / "ui").glob("*/manifest.json")))

        failures = []
        for manifest_path in manifest_paths:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            missing = _array_paths_missing_items(payload)
            if missing:
                failures.append(f"{manifest_path}: {', '.join(missing)}")

        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
