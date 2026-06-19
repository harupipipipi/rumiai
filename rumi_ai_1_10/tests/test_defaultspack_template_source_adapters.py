from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.templates.projectors import build_template_catalog  # noqa: E402
from domain.templates.source_adapters import (  # noqa: E402
    LegacyCommandTemplateAdapter,
    discover_source_adapter_contributions,
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_source_adapters_discover_read_only_contributions_with_attribution(tmp_path):
    _write_json(
        tmp_path / "components" / "chat" / "manifest.json",
        {"id": "chat", "kind": "component", "trust_level": "builtin"},
    )
    _write_json(
        tmp_path / "extensions" / "ui" / "default" / "manifest.json",
        {"id": "default_ui", "category": "ui"},
    )
    _write_json(
        tmp_path / "commands" / "default_commands.json",
        [{"id": "help", "execution": {"type": "frontend", "action": "help"}}],
    )
    _write_text(
        tmp_path / "external_io_templates" / "line.input.default.template.yaml",
        "id: line.input.default\nprovider: line\n",
    )
    _write_text(
        tmp_path / "flows" / "chat_turn.flow.yaml",
        """
flow_id: defaultspack.chat_turn
transport:
  http:
    routes:
      - method: POST
        path: /api/chat
""",
    )

    result = discover_source_adapter_contributions(tmp_path)
    items = [item.to_catalog_item() for item in result.contributions]

    assert not result.diagnostics
    assert {item["source_kind"] for item in items} >= {
        "domain_component",
        "extension_manifest",
        "legacy_command",
        "external_io_template",
        "flow_route",
    }
    assert all(item["_metadata_only"] is True for item in items)
    assert all(item["source_pack_id"] == "defaultspack" for item in items)
    assert all(item["trust_level"] == "builtin" for item in items)


def test_source_adapters_do_not_double_register_legacy_commands(tmp_path):
    _write_json(
        tmp_path / "commands" / "default_commands.json",
        [{"id": "help", "execution": {"type": "frontend", "action": "help"}}],
    )

    catalog = build_template_catalog(
        defaultspack_root=tmp_path,
        adapters=[LegacyCommandTemplateAdapter()],
    )

    assert catalog["commands"] == []
    assert [item["public_id"] for item in catalog["source_adapter_contributions"]] == [
        "legacy_command:help"
    ]


def test_source_adapter_trust_is_authoritative_for_user_manifest(tmp_path):
    _write_json(
        tmp_path / "user_data" / "shared" / "commands" / "custom.json",
        [{"id": "custom", "trust_level": "builtin"}],
    )

    catalog = build_template_catalog(
        defaultspack_root=tmp_path,
        adapters=[LegacyCommandTemplateAdapter()],
    )

    item = catalog["source_adapter_contributions"][0]
    assert item["trust_level"] == "user"
    assert "trust_level" not in item["metadata"]["command"]


def test_source_adapter_collisions_use_common_catalog_diagnostic(tmp_path):
    _write_json(tmp_path / "commands" / "default_commands.json", [{"id": "same"}])
    _write_json(tmp_path / "commands" / "manifests" / "extra.json", [{"id": "same"}])

    catalog = build_template_catalog(
        defaultspack_root=tmp_path,
        adapters=[LegacyCommandTemplateAdapter()],
    )

    assert catalog["source_adapter_contributions"] == []
    assert any(
        diagnostic.get("code") == "template.catalog.public_id_collision"
        and diagnostic.get("details", {}).get("bucket") == "source_adapter_contributions"
        for diagnostic in catalog["template_diagnostics"]
    )


def test_source_adapter_malformed_source_fails_soft(tmp_path):
    _write_text(tmp_path / "commands" / "default_commands.json", "{not json")

    catalog = build_template_catalog(
        defaultspack_root=tmp_path,
        adapters=[LegacyCommandTemplateAdapter()],
    )

    assert catalog["source_adapter_contributions"] == []
    assert any(
        diagnostic.get("code") == "template.source_adapter.invalid_json"
        for diagnostic in catalog["template_diagnostics"]
    )


def test_source_adapters_can_be_disabled_for_activation_selection(tmp_path):
    _write_json(tmp_path / "commands" / "default_commands.json", [{"id": "help"}])

    catalog = build_template_catalog(defaultspack_root=tmp_path, adapters=[])

    assert catalog["source_adapter_contributions"] == []
