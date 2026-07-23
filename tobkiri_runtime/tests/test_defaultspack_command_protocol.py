from __future__ import annotations

import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.frontend.command_protocol import (  # noqa: E402
    CommandProtocolRegistry,
    CommandProtocolSchemaError,
    validate_protocol_document,
)
from transport.registry import (  # noqa: E402
    canonical_http_route_specs,
    require_legacy_route_allowlisted,
)


def test_resolved_catalog_projects_all_legacy_commands_to_v1() -> None:
    catalog = CommandProtocolRegistry(DEFAULTSPACK_ROOT).catalog()

    assert catalog["api_version"] == "tobkiri.commands/v1"
    assert len(catalog["commands"]) == 55
    assert len({item["canonical_id"] for item in catalog["commands"]}) == 55
    assert {
        item["execution"]["kind"] for item in catalog["commands"]
    } <= {"state_mutation", "host_operation", "pack_operation"}
    assert {
        item["presentation"]["input"]["kind"] for item in catalog["commands"]
    } <= {"search_select", "select", "toggle", "action", "form"}

    by_id = {item["identity"]["id"]: item for item in catalog["commands"]}
    assert by_id["deepthink"]["presentation"]["input"]["kind"] == "toggle"
    assert by_id["deepthink"]["execution"]["kind"] == "state_mutation"
    assert by_id["model"]["presentation"]["input"]["kind"] == "search_select"
    assert by_id["model"]["presentation"]["input"]["datasource_ref"] == "tobkiri:model_catalog"
    assert by_id["home_title"]["execution"]["operation_ref"] == "host:set_home_title"
    assert by_id["home_title"]["presentation"]["input"]["kind"] == "form"
    assert by_id["home_title"]["presentation"]["input"]["fields"][0]["placeholder"] == {
        "fallback": "表示したい文字を入力"
    }


def test_resolved_catalog_never_silently_exposes_missing_frontend_handler() -> None:
    catalog = CommandProtocolRegistry(DEFAULTSPACK_ROOT).catalog()
    unavailable = [
        item
        for item in catalog["commands"]
        if item["availability"]["status"] == "unavailable"
    ]

    assert unavailable
    assert all(
        item["availability"]["reason_code"] == "handler_missing"
        for item in unavailable
    )
    assert any(item["code"] == "handler_missing" for item in catalog["diagnostics"])


def test_protocol_deepthink_invocation_returns_authoritative_state(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv(
        "RUMI_DEFAULTSPACK_FRONTEND_SETTINGS_PATH",
        str(tmp_path / "frontend_settings.json"),
    )
    protocol = CommandProtocolRegistry(DEFAULTSPACK_ROOT)

    enabled = protocol.invoke(
        {
            "command_ref": "defaultspack:deepthink",
            "args": {"enabled": True},
            "mode": "chat",
            "invocation_id": "deepthink-protocol-1",
            "idempotency_key": "deepthink-protocol-1",
            "expected_revision": 0,
        }
    )
    disabled = protocol.invoke(
        {
            "command_ref": "defaultspack:deepthink",
            "args": {"enabled": False},
            "mode": "chat",
            "invocation_id": "deepthink-protocol-2",
            "idempotency_key": "deepthink-protocol-2",
            "expected_revision": 1,
        }
    )

    assert enabled["status"] == "succeeded"
    assert enabled["state_changes"][0]["value"] is True
    assert enabled["state_changes"][0]["revision"] == 1
    assert disabled["state_changes"][0]["value"] is False
    assert disabled["state_changes"][0]["revision"] == 2


def test_home_title_invocation_returns_frontend_action() -> None:
    result = CommandProtocolRegistry(DEFAULTSPACK_ROOT).invoke(
        {
            "command_ref": "defaultspack:home_title",
            "args": {"value": "My Tobkiri"},
        }
    )

    assert result["status"] == "succeeded"
    assert result["legacy_result"]["action"] == "set_home_title"
    assert result["legacy_result"]["args"] == {"value": "My Tobkiri"}


def test_model_datasource_returns_standard_option_items() -> None:
    result = CommandProtocolRegistry(DEFAULTSPACK_ROOT).query_datasource(
        {"datasource_ref": "tobkiri:model_catalog", "query": "stub", "limit": 10}
    )

    assert result["status"] == "succeeded"
    assert result["items"]
    item = result["items"][0]
    assert item["value"]
    assert item["label"]["fallback"]
    assert "provider_id" in item["metadata"]


def test_provider_datasource_uses_same_option_item_contract() -> None:
    result = CommandProtocolRegistry(DEFAULTSPACK_ROOT).query_datasource(
        {"datasource_ref": "tobkiri:provider_catalog", "limit": 100}
    )

    assert result["status"] == "succeeded"
    assert result["items"]
    assert all(item["value"] and item["label"]["fallback"] for item in result["items"])
    assert all("model_count" in item["metadata"] for item in result["items"])


def test_protocol_schema_rejects_unknown_normative_fields_and_major() -> None:
    catalog = CommandProtocolRegistry(DEFAULTSPACK_ROOT).catalog()
    catalog["unexpected"] = True
    try:
        validate_protocol_document(catalog)
    except CommandProtocolSchemaError:
        pass
    else:
        raise AssertionError("unknown normative field must be rejected")

    catalog.pop("unexpected")
    catalog["api_version"] = "tobkiri.commands/v2"
    try:
        validate_protocol_document(catalog)
    except CommandProtocolSchemaError:
        pass
    else:
        raise AssertionError("unsupported major must be rejected")


def test_settings_registered_command_is_resolved_and_invoked_through_protocol(
    tmp_path: Path, monkeypatch
) -> None:
    settings_path = tmp_path / "frontend_settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "commands": {
                    "registered_slash_commands": [
                        {
                            "name": "go",
                            "action": "toggle_yolo",
                            "aliases": ["ship it"],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("RUMI_DEFAULTSPACK_FRONTEND_SETTINGS_PATH", str(settings_path))
    protocol = CommandProtocolRegistry(DEFAULTSPACK_ROOT)

    command = next(
        item for item in protocol.catalog()["commands"] if item["identity"]["name"] == "go"
    )
    result = protocol.invoke(
        {"command_ref": command["canonical_id"], "args": {"enabled": True}, "mode": "chat"}
    )

    assert command["legacy"]["source"] == "settings.registered_slash_commands"
    assert command["presentation"]["input"]["kind"] == "toggle"
    assert command["identity"]["aliases"] == ["ship_it"]
    assert result["status"] == "succeeded"
    assert result["legacy_result"]["action"] == "toggle_yolo"


def test_command_protocol_routes_are_registered() -> None:
    specs = canonical_http_route_specs()
    routes = {(item.method, item.pattern) for item in specs}
    assert ("GET", "/api/command-protocol/v1/catalog") in routes
    assert ("POST", "/api/command-protocol/v1/invoke") in routes
    assert ("POST", "/api/command-protocol/v1/states/query") in routes
    assert ("POST", "/api/command-protocol/v1/datasources/query") in routes

    protocol_specs = [
        item for item in specs if item.pattern.startswith("/api/command-protocol/v1/")
    ]
    assert len(protocol_specs) == 4
    for item in protocol_specs:
        require_legacy_route_allowlisted(item)
