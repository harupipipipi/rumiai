"""Protocol coverage for declarative AI provider connection metadata."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from tobkiri_protocol.errors import SchemaValidationError
from tobkiri_protocol.validation import validate_document


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "conformance_minimal_echo_pack"
    / "contracts.v4.json"
)


def _catalog(auth_mode: str) -> dict[str, object]:
    catalog = json.loads(FIXTURE.read_text(encoding="utf-8"))
    contract = catalog["contracts"][0]
    contract["provider_semantics"]["connection"] = {
        "kind": "ai_provider",
        "instance_id": f"fixture.{auth_mode.replace('_', '-')}",
        "display_name": f"Fixture {auth_mode}",
        "auth_modes": [auth_mode],
        "settings_schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {"endpoint": {"type": "string"}},
        },
        "ui_hints": {"endpoint": "Provider endpoint"},
        "secret_fields": ["api_key"] if auth_mode == "api_key" else [],
        "endpoint_requirements": {
            "network_required": auth_mode != "none",
            "local_allowed": auth_mode == "none",
        },
        "operations": {"test": "echo"},
        "multi_instance": True,
        "instance_field": "provider_instance_id",
        "configured": auth_mode == "none",
        "credential_present": False,
        "status": "healthy" if auth_mode == "none" else "not_configured",
        "model_count": None,
        "last_refresh_at": None,
    }
    return catalog


@pytest.mark.parametrize("auth_mode", ["api_key", "oauth", "none", "custom_auth"])
def test_connection_metadata_is_provider_neutral_and_schema_valid(auth_mode: str) -> None:
    """Any conforming auth mode validates without a built-in provider registry."""
    document = _catalog(auth_mode)
    assert validate_document(document, "pack_contract_catalog") == document


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("access_token", "must-not-be-accepted"),
        ("ui_hints", {"endpoint": {"unsafe": "shape"}}),
        ("settings_schema", {"type": "array"}),
    ],
)
def test_malformed_or_secret_bearing_connection_metadata_fails_closed(
    field: str,
    value: object,
) -> None:
    """Malformed UI metadata and secret material never enter the v4 catalog."""
    document = deepcopy(_catalog("api_key"))
    document["contracts"][0]["provider_semantics"]["connection"][field] = value
    with pytest.raises(SchemaValidationError):
        validate_document(document, "pack_contract_catalog")
