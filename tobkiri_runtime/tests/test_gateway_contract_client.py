"""Compatibility tests for the global-contract-backed chat gateway."""

import json
from pathlib import Path

import pytest

from ecosystem.defaultspack.domain.ai_client import gateway_contract_client
from ecosystem.defaultspack.domain.ai_client.gateway_contract_client import (
    ContractLLMGateway,
)
from ecosystem.rumi_provider_adapters_pack.runtime.adapter import (
    _adapter,
    _connection,
    _provider_model_id,
)

pytestmark = pytest.mark.contract


def test_contract_gateway_reports_its_stream_implementation() -> None:
    gateway = ContractLLMGateway()

    assert gateway.supports_stream("openrouter/tencent/hy3:free") is True
    assert gateway.supports_stream("") is False


def test_contract_gateway_binds_active_startup_profile(monkeypatch) -> None:
    captured = {}

    class Container:
        def get_or_none(self, _key):
            return object()

    monkeypatch.setattr(gateway_contract_client, "get_container", lambda: Container())
    monkeypatch.setattr(
        gateway_contract_client,
        "active_profile_id",
        lambda: "defaults-profile",
    )

    def invoke(_registry, _contract, _operation, payload):
        captured.update(payload)
        return {"events": []}

    monkeypatch.setattr(gateway_contract_client, "invoke_global_contract", invoke)

    assert gateway_contract_client.stream({"messages": []}) == []
    assert captured["profile_id"] == "defaults-profile"


def test_contract_gateway_migrates_legacy_connection_once(monkeypatch) -> None:
    class Container:
        def get_or_none(self, _key):
            return object()

    calls = []
    monkeypatch.setattr(gateway_contract_client, "get_container", lambda: Container())
    monkeypatch.setattr(gateway_contract_client, "active_profile_id", lambda: "default-profile")
    monkeypatch.setattr(
        gateway_contract_client,
        "_migrate_legacy_connection",
        lambda payload: payload["model_reference"] == "opencode-zen/model",
    )

    def invoke(_registry, _contract, _operation, payload):
        calls.append(dict(payload))
        if len(calls) == 1:
            raise gateway_contract_client.GlobalContractInvocationError(
                "not_configured",
                "provider connection is not configured",
            )
        return {"output": "ok"}

    monkeypatch.setattr(gateway_contract_client, "invoke_global_contract", invoke)

    result = gateway_contract_client.generate(
        {"model_reference": "opencode-zen/model"},
    )

    assert result["content"] == "ok"
    assert len(calls) == 2


def test_contract_gateway_does_not_retry_unrelated_failures(monkeypatch) -> None:
    class Container:
        def get_or_none(self, _key):
            return object()

    monkeypatch.setattr(gateway_contract_client, "get_container", lambda: Container())
    monkeypatch.setattr(gateway_contract_client, "active_profile_id", lambda: "default-profile")
    monkeypatch.setattr(
        gateway_contract_client,
        "_migrate_legacy_connection",
        lambda _payload: (_ for _ in ()).throw(AssertionError("must not migrate")),
    )
    monkeypatch.setattr(
        gateway_contract_client,
        "invoke_global_contract",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            gateway_contract_client.GlobalContractInvocationError(
                "denied",
                "provider access denied",
            )
        ),
    )

    try:
        gateway_contract_client.generate({"model_reference": "opencode-zen/model"})
    except gateway_contract_client.GlobalContractInvocationError as exc:
        assert exc.code == "denied"
    else:
        raise AssertionError("expected provider failure")


def test_provider_adapter_instance_matches_catalog_execution_hint() -> None:
    """Keep catalog models routable to the shared compatibility adapter."""
    ecosystem = Path(__file__).parents[1] / "ecosystem"
    adapter_manifest = json.loads(
        (
            ecosystem / "rumi_provider_adapters_pack" / "rumi.pack.v3.json"
        ).read_text(encoding="utf-8")
    )
    providers = adapter_manifest["contracts"]["provides"]

    assert len({provider["provider_instance_id"] for provider in providers}) == 4
    assert all(provider["routing_keys"] == ["*"] for provider in providers)


def test_openrouter_uses_the_openai_compatible_protocol() -> None:
    assert _adapter("openrouter") is _adapter("openai-compatible")
    assert _adapter("llm", provider_id="openrouter") is _adapter(
        "openai-compatible"
    )


def test_openrouter_model_id_drops_provider_prefix() -> None:
    assert _provider_model_id(
        {
            "provider_id": "openrouter",
            "model_id": "openrouter/tencent/hy3:free",
        }
    ) == "tencent/hy3:free"


def test_provider_connection_lookup_is_bound_to_startup_profile() -> None:
    class RegistryClient:
        def __init__(self) -> None:
            self.payload = None

        def invoke(self, _contract, _operation, payload):
            self.payload = dict(payload)
            return {
                "providers": [
                    {
                        "provider_instance_id": "provider.openrouter",
                        "enabled": True,
                    }
                ]
            }

    client = RegistryClient()

    connection = _connection(
        client,  # type: ignore[arg-type]
        {"provider_id": "openrouter", "profile_id": "defaults-profile"},
    )

    assert connection["provider_instance_id"] == "provider.openrouter"
    assert client.payload == {"profile_id": "defaults-profile"}
