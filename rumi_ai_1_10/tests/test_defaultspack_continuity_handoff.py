from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


@pytest.fixture()
def continuity_env(tmp_path, monkeypatch):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CONTINUITY_DIR", str(tmp_path / "continuity"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_SECRETS_DIR", str(tmp_path / "secrets"))
    for key in ("OPENAI_API_KEY", "OLLAMA_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    yield tmp_path


def _save_named_key(provider_id: str, api_id: str, value: str, **metadata):
    from domain.ai_client.api_key_store import set_provider_api_key

    result = set_provider_api_key(provider_id, value, api_id=api_id, **metadata)
    assert result["success"] is True
    return result


def test_provider_route_preserves_exact_named_api_route_and_blocks_local(continuity_env):
    from ecosystem.defaultspack.backend.continuity import ContinuityCoordinator

    _save_named_key(
        "openai",
        "primary",
        "test-openai-secret",
        default_model="gpt-4.1",
        allowed_models=["gpt-4.1"],
    )
    _save_named_key(
        "ollama",
        "local",
        "test-ollama-secret",
        base_url="http://127.0.0.1:11434/v1",
        default_model="llama3",
        allowed_models=["llama3"],
    )
    coordinator = ContinuityCoordinator()
    destination = coordinator.node_registry.register_destination(display_name="Workstation")

    routes = coordinator.list_provider_routes()["routes"]
    openai_route = next(route for route in routes if route["provider_id"] == "openai" and route["api_id"] == "primary")
    ollama_route = next(route for route in routes if route["provider_id"] == "ollama" and route["api_id"] == "local")

    assert openai_route["qualified_route"] == "openai/primary/gpt-4.1"
    assert openai_route["credential_ref"].startswith("RUMIAPI_OPENAI_PRIMARY")
    assert openai_route["portable"] is True
    assert ollama_route["portable"] is False
    assert ollama_route["blocked_reason"] == "LOCAL_MODEL_PROVIDER_NOT_PORTABLE"

    probe = coordinator.probe_provider_route(
        {
            "route_id": openai_route["route_id"],
            "destination_node_id": destination["node_id"],
        }
    )
    assert probe["ok"] is True
    assert {check["code"] for check in probe["checks"]} >= {"DESTINATION_ENDPOINT_REACHABLE", "CREDENTIAL_REFERENCE_CONFIGURED"}


def test_handoff_creates_encrypted_credential_envelope_and_atomic_primary_lease(continuity_env):
    from ecosystem.defaultspack.backend.continuity import ContinuityCoordinator

    secret = "test-provider-secret-value"
    _save_named_key(
        "openai",
        "primary",
        secret,
        default_model="gpt-4.1",
        allowed_models=["gpt-4.1"],
    )
    coordinator = ContinuityCoordinator()
    destination = coordinator.node_registry.register_destination(display_name="Workstation")

    result = coordinator.start_handoff(
        {
            "sandbox_id": "sandbox-123",
            "destination_node_id": destination["node_id"],
            "provider_id": "openai",
            "api_id": "primary",
            "model_id": "gpt-4.1",
            "mode": "move",
        }
    )

    operation = result["operation"]
    assert operation["status"] == "COMPLETED"
    assert operation["destination_primary"] is True
    assert operation["source_primary"] is False
    assert operation["primary_lease"]["owner_node_id"] == destination["node_id"]
    assert operation["primary_lease"]["generation"] == 2

    envelope = coordinator.credentials.get(operation["credential_envelope_id"])
    assert envelope is not None
    assert secret not in json.dumps(envelope)
    unwrapped = coordinator.credentials.unwrap(
        envelope,
        destination_private_key=coordinator.node_registry.private_key_for(destination["node_id"]),
    )
    assert unwrapped["secret"] == secret
    assert unwrapped["allowed_model_ids"] == ["gpt-4.1"]

    continuity_text = (Path(os.environ["RUMI_DEFAULTSPACK_CONTINUITY_DIR"]) / "credential_envelopes.json").read_text(encoding="utf-8")
    assert secret not in continuity_text
    checkpoint_text = (Path(os.environ["RUMI_DEFAULTSPACK_CONTINUITY_DIR"]) / "checkpoints.json").read_text(encoding="utf-8")
    assert secret not in checkpoint_text
    assert "credential_envelope_id" in checkpoint_text


def test_handoff_pauses_when_preflight_rejects_source_only_provider(continuity_env):
    from ecosystem.defaultspack.backend.continuity import ContinuityCoordinator

    _save_named_key(
        "ollama",
        "local",
        "test-ollama-secret",
        base_url="http://127.0.0.1:11434/v1",
        default_model="llama3",
        allowed_models=["llama3"],
    )
    coordinator = ContinuityCoordinator()
    destination = coordinator.node_registry.register_destination(display_name="Workstation")

    result = coordinator.start_handoff(
        {
            "sandbox_id": "sandbox-local",
            "destination_node_id": destination["node_id"],
            "provider_id": "ollama",
            "api_id": "local",
            "model_id": "llama3",
        }
    )

    operation = result["operation"]
    assert operation["status"] == "PAUSED_USER_ACTION"
    assert operation["plan"]["status"] == "blocked"
    errors = operation["plan"]["resource_preflight"]["errors"]
    assert errors[0]["code"] == "LOCAL_MODEL_PROVIDER_NOT_PORTABLE"


def test_checkpoint_manifest_rejects_secret_looking_state(continuity_env):
    from ecosystem.defaultspack.backend.continuity import ContinuityCoordinator
    from ecosystem.defaultspack.backend.continuity.errors import ContinuityError

    _save_named_key(
        "openai",
        "primary",
        "test-openai-secret",
        default_model="gpt-4.1",
        allowed_models=["gpt-4.1"],
    )
    coordinator = ContinuityCoordinator()
    with pytest.raises(ContinuityError) as exc:
        coordinator.checkpoint(
            {
                "sandbox_id": "sandbox-secret",
                "provider_id": "openai",
                "api_id": "primary",
                "model_id": "gpt-4.1",
                "state": {"api_key": "should-not-be-here"},
            }
        )
    assert exc.value.code == "CHECKPOINT_SECRET_LEAK"


def test_continuity_routes_and_ai_functions_are_registered():
    from domain.function_runtime.registry import get_spec
    from transport.registry import canonical_http_route_specs

    assert get_spec("continuity_handoff").risk == "high"
    assert "continuity.handoff" in get_spec("continuity_handoff").aliases
    assert get_spec("continuity_plan_handoff").block_module == "blocks.continuity.api"

    routes = {(spec.method, spec.pattern, spec.function_id) for spec in canonical_http_route_specs()}
    assert ("GET", "/api/continuity/nodes", "continuity_list_nodes") in routes
    assert ("POST", "/api/continuity/handoffs", "continuity_handoff") in routes
    assert ("POST", "/api/continuity/provider-routes/{route_id}/probe", "continuity_probe_provider_route") in routes
