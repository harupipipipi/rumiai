from __future__ import annotations

import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent.parent
PACK_ROOT = ROOT / "ecosystem" / "rumi_browser_element_pack"


def _browser_companion_extension_root() -> Path:
    candidates = [
        ROOT / "ecosystem" / "defaultspack" / "browser_extensions" / "rumi_browser_companion",
        ROOT.parent / "browser_extensions" / "rumi_browser_companion",
    ]
    for candidate in candidates:
        if (candidate / "content_script.js").is_file():
            return candidate
    return candidates[0]


def test_browser_element_pack_has_required_docs() -> None:
    for relative in (
        "README.md",
        "docs/README.md",
        "docs/architecture.md",
        "docs/interfaces.md",
        "docs/operations.md",
    ):
        path = PACK_ROOT / relative
        assert path.is_file(), relative
        assert path.read_text(encoding="utf-8").strip()


def test_browser_element_pack_json_and_yaml_parse() -> None:
    json.loads((PACK_ROOT / "ecosystem.json").read_text(encoding="utf-8"))
    json.loads(
        (ROOT / "ecosystem" / "setup_pack" / "rumi_browser_element_pack" / "pack.json").read_text(
            encoding="utf-8"
        )
    )
    for path in PACK_ROOT.rglob("*.yaml"):
        assert yaml.safe_load(path.read_text(encoding="utf-8")) is not None, path


def test_browser_element_pack_tracks_extension_semantic_contract() -> None:
    content = (_browser_companion_extension_root() / "content_script.js").read_text(encoding="utf-8")
    schema = yaml.safe_load((PACK_ROOT / "catalog" / "element_schema.yaml").read_text(encoding="utf-8"))

    assert schema["schema_id"] == "rumi.browser.semantic_dom_v2"
    for field in schema["required_fields"]:
        assert field in content
    assert "page.highlight" in content
