from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_mobile_bootstrap_returns_server_and_capability_flags():
    from blocks.mobile.bootstrap import run

    result = run({}, None)
    assert result["status"] == "ok"
    data = result["data"]
    assert "server" in data
    assert {"device_id", "label", "version"} <= set(data["server"])
    caps = data["capabilities"]
    assert caps["chat"] is True
    assert caps["tools"] is True
    assert "credential_transfer" in caps
    assert "cursor" in data


def test_mobile_capabilities_returns_provider_and_model_catalogs():
    from blocks.mobile.capabilities import run

    result = run({}, None)
    assert result["status"] == "ok"
    data = result["data"]
    assert len(data["providers"]) > 0
    assert len(data["models"]) > 0

    provider = data["providers"][0]
    assert "provider_id" in provider
    assert "display_name" in provider
    assert "configured" in provider
    # Secrets must not leak: only env var names, never values.
    assert all(isinstance(name, str) for name in provider.get("env_vars", []))
    assert "api_key" not in str(provider).lower() or provider.get("configured_api_count") is not None

    model = data["models"][0]
    assert "id" in model
    assert "provider_id" in model
    assert "model_id" in model
    assert "max_context" in model


def test_mobile_capabilities_provider_filter_narrows_models():
    from blocks.mobile.capabilities import run

    all_models = run({}, None)["data"]["models"]
    if not all_models:
        return
    provider_id = all_models[0]["provider_id"]
    filtered = run({"provider": provider_id}, None)["data"]["models"]
    assert filtered
    assert all(m["provider_id"] == provider_id for m in filtered)


def test_mobile_capabilities_query_param_provider_filter():
    from blocks.mobile.capabilities import run

    all_models = run({}, None)["data"]["models"]
    if not all_models:
        return
    provider_id = all_models[0]["provider_id"]
    filtered = run({"query_params": {"provider": provider_id}}, None)["data"]["models"]
    assert filtered
    assert all(m["provider_id"] == provider_id for m in filtered)


def test_mobile_capabilities_include_templates_flag():
    from blocks.mobile.capabilities import run

    with_templates = run({"include_templates": True}, None)["data"]
    without = run({"include_templates": False}, None)["data"]
    assert "templates" in with_templates
    assert "templates" in without
    assert without["templates"] == []


def test_mobile_capabilities_no_secret_values_in_provider_entries():
    from blocks.mobile.capabilities import run

    providers = run({}, None)["data"]["providers"]
    blob = str(providers)
    # Active HMAC keys / API key values must never appear in catalog payloads.
    forbidden = ["sk-", "Bearer ", "hmac_secret"]
    for token in forbidden:
        assert token not in blob, f"unexpected secret token in catalog: {token}"


def test_mobile_capabilities_provider_summary_has_openai_compatible_flag():
    from blocks.mobile.capabilities import run

    providers = run({}, None)["data"]["providers"]
    assert any("openai_compatible" in p for p in providers)
