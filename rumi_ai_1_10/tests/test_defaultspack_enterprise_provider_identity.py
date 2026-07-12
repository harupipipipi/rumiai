from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
DEFAULTSPACK = ROOT / "ecosystem" / "defaultspack"
if str(DEFAULTSPACK) not in sys.path:
    sys.path.insert(0, str(DEFAULTSPACK))

from domain.ai_client.enterprise_provider_identity import (  # noqa: E402
    IDENTITY_FIELDS,
    enterprise_scope,
    normalize_enterprise_identity,
    qualified_deployment_id,
)
from domain.ai_client.providers import get_provider_catalog_map  # noqa: E402
from domain.components.registry import get_domain_component_registry  # noqa: E402


def _identity(provider_id):
    return {field: f"private-{field}" for field in IDENTITY_FIELDS[provider_id]}


def test_enterprise_scope_is_stable_isolated_and_opaque(tmp_path):
    key = tmp_path / "scope.key"
    first = enterprise_scope("aws-bedrock", _identity("aws-bedrock"), key_path=key)
    same = enterprise_scope("aws-bedrock", _identity("aws-bedrock"), key_path=key)
    changed = enterprise_scope("aws-bedrock", {**_identity("aws-bedrock"), "region": "other"}, key_path=key)
    assert first == same
    assert first != changed
    assert "private" not in first


def test_deployment_qualification_never_flattens_control_plane_identity(tmp_path, monkeypatch):
    monkeypatch.setattr("domain.ai_client.enterprise_provider_identity._local_key", lambda _path: b"x" * 32)
    identity = _identity("azure-openai")
    qualified = qualified_deployment_id("azure-openai", identity, "gpt-family")
    assert qualified.startswith("azure-openai/")
    assert qualified.endswith(":gpt-family")
    assert identity["resource"] not in qualified
    assert identity["deployment"] not in qualified


def test_enterprise_identity_rejects_missing_dimensions():
    with pytest.raises(ValueError, match="endpoint"):
        normalize_enterprise_identity("databricks-model-serving", {"workspace": "one"})


def test_enterprise_matrix_registered_with_explicit_native_boundaries():
    get_domain_component_registry(force_reload=True)
    catalog = get_provider_catalog_map()
    assert set(IDENTITY_FIELDS) <= set(catalog)
    for provider_id, fields in IDENTITY_FIELDS.items():
        payload = json.loads((DEFAULTSPACK / "domain" / "providers" / provider_id / "manifest.json").read_text(encoding="utf-8"))
        manifest = payload["provider_manifest"]
        assert manifest["config"]["identity_fields"] == list(fields)
        assert manifest["config"]["inventory_scope"] == "account_project_region"
        assert manifest["config"]["source_docs"].startswith("https://")
        assert "default_model" not in manifest
        if manifest["adapter"] not in {"openai_compatible"}:
            assert manifest["supports_invoke"] is False
            assert manifest["catalog_only"] is True
