from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any
from dataclasses import replace

import pytest

from ecosystem.rumi_credential_broker_pack.runtime import store as store_module
from ecosystem.rumi_credential_broker_pack.runtime.store import CredentialBrokerStore
from core_runtime.credential_transport import (
    CredentialTransportDenied,
    HostBoundCredentialTransport,
)
from core_runtime.global_contract_dispatch import GlobalContractClient
from ecosystem.rumi_credential_broker_pack.runtime.service import (
    CredentialBrokerService,
)
from ecosystem.rumi_provider_adapters_pack.runtime.adapter import (
    REGISTRY_CONTRACT,
    REGISTRY_OPERATION,
    create_generate_operation,
)
from tests.test_authority_v4_lifecycle import _Harness
from tests.test_tobkiri_host_authority_v4_adapter import (
    _adapter,
    _context,
    _digest,
    _queries,
)
from tobkiri_host.broker import RequestEnvelope
from tobkiri_host.models import OpaqueAuthorityRef


class _Response:
    def __init__(self, value: dict[str, Any]) -> None:
        self._value = value

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._value).encode("utf-8")


def test_windows_credential_root_acl_is_hardened_with_argument_vector(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[list[str], dict[str, Any]]] = []

    def _run(argv: list[str], **kwargs: Any) -> None:
        calls.append((argv, kwargs))

    monkeypatch.setattr(store_module.subprocess, "run", _run)
    store_module._secure_windows_directory(tmp_path)

    assert len(calls) == 1
    argv, kwargs = calls[0]
    assert argv[:5] == [
        "powershell.exe",
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
    ]
    assert len(argv) == 6
    assert str(tmp_path) not in argv
    assert "$target = [Console]::In.ReadToEnd()" in argv[-1]
    assert "SetAccessRuleProtection($true, $false)" in argv[-1]
    assert "Access.Count -ne 1" in argv[-1]
    assert kwargs == {
        "check": True,
        "capture_output": True,
        "text": True,
        "timeout": 15,
        "input": str(tmp_path),
    }


def test_windows_credential_root_acl_failure_is_redacted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _run(*_args: object, **_kwargs: object) -> None:
        raise store_module.subprocess.CalledProcessError(
            1,
            ["powershell.exe"],
            output="sensitive stdout",
            stderr="sensitive stderr",
        )

    monkeypatch.setattr(store_module.subprocess, "run", _run)
    with pytest.raises(PermissionError) as caught:
        store_module._secure_windows_directory(tmp_path)
    assert str(caught.value) == "credential Windows ACL could not be secured"
    assert "sensitive" not in str(caught.value)


def test_windows_credential_root_acl_is_applied_once_per_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = CredentialBrokerStore(user_data_root=tmp_path)
    secured: list[Path] = []
    monkeypatch.setattr(store_module.os, "name", "nt")
    monkeypatch.setattr(store_module, "_secure_windows_directory", secured.append)

    store._prepare_storage()
    store._prepare_storage()

    assert secured == [store.root]


def _dispatched_envelope(
    tmp_path: Path,
) -> tuple[_Harness, RequestEnvelope]:
    authority = _Harness(tmp_path / "authority")
    adapter = _adapter(authority)
    context = _context(authority)
    request_digest = _digest("credential-provider-request")
    _static, final = _queries(authority, context, request_digest)
    lease = adapter.authorize_and_issue_lease(final)
    adapter.recheck_effect_boundary(
        context,
        OpaqueAuthorityRef(authority.target.principal_id),
        lease,
    )
    return authority, RequestEnvelope(
        context=context,
        target_principal=OpaqueAuthorityRef(authority.target.principal_id),
        target_domain=OpaqueAuthorityRef(authority.target_domain.domain_id),
        contract_id="host.http",
        contract_version="1.0.0",
        operation_id=authority.target.operation_id,
        payload={"credential_handle": "opaque"},
        request_digest=request_digest,
        deadline_monotonic=9_999_999_999.0,
        lease=lease,
        idempotency_key=None,
    )


def test_credential_material_is_encrypted_and_listing_is_redacted(
    tmp_path: Path,
) -> None:
    service = CredentialBrokerService(user_data_root=tmp_path)

    created = service.invoke(
        "create",
        {
            "secret_material": {"api_key": "fixture-secret"},
            "profile_id": "profile-a",
            "consumer_pack_id": "provider-adapter-pack",
            "provider_instance_id": "provider.adapter-main",
            "scopes": ["generate", "stream"],
            "label": "fixture",
        },
    )
    listed = service.invoke("list", {"profile_id": "profile-a"})

    store_text = service.store.path.read_text(encoding="utf-8")
    assert "fixture-secret" not in store_text
    assert "ciphertext" not in str(listed)
    assert "secret_material" not in str(listed)
    assert created["handle"].startswith("credential:")
    restarted = CredentialBrokerService(user_data_root=tmp_path)
    restarted_list = restarted.invoke("list", {"profile_id": "profile-a"})
    assert restarted_list["credentials"][0]["handle"] == created["handle"]
    assert "fixture-secret" not in restarted.store.path.read_text(encoding="utf-8")


def test_generic_resolution_is_denied_and_host_transport_applies_once(
    tmp_path: Path,
) -> None:
    service = CredentialBrokerService(user_data_root=tmp_path)
    created = service.invoke(
        "create",
        {
            "secret_material": {"api_key": "fixture-secret"},
            "profile_id": "profile-1",
            "consumer_pack_id": "provider-adapter-pack",
            "provider_instance_id": "provider.adapter-main",
            "scopes": ["ai.generate"],
        },
    )

    with pytest.raises(PermissionError, match="Host transport"):
        service.invoke(
            "resolve",
            {
                "_contract_consumer_pack_id": "provider-adapter-pack",
                "handle": created["handle"],
                "provider_instance_id": "provider.adapter-main",
                "scope": "generate",
                "profile_id": "profile-1",
            },
        )

    authority, envelope = _dispatched_envelope(tmp_path)
    audit: list[dict[str, Any]] = []
    observed_authorization = []

    def opener(request, *, timeout):
        del timeout
        observed_authorization.append(request.get_header("Authorization"))
        return _Response(
            {
                "choices": [
                    {
                        "message": {"content": "fixture-secret must be redacted"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {},
            }
        )

    transport = HostBoundCredentialTransport.from_authorized_envelope(
        envelope,
        provider_principal=authority.target,
        store=service.store,
        authority_store=authority.store,
        credential_handle=created["handle"],
        credential_key_version=created["key_version"],
        provider_instance_id="provider.adapter-main",
        credential_scope="ai.generate",
        credential_purpose="provider.invoke",
        endpoint_origin="https://provider.example",
        current_security_epoch=lambda: authority.store.security_epoch,
        consumer_pack_id="provider-adapter-pack",
        opener=opener,
        audit_sink=lambda event: audit.append(dict(event)),
    )

    class CapturedSession:
        profile_id = "profile-1"
        plan_digest = _digest("credential-provider-plan")

        def invoke(self, contract_id, operation_id, payload, **_kwargs):
            assert (contract_id, operation_id, payload) == (
                REGISTRY_CONTRACT,
                REGISTRY_OPERATION,
                {"profile_id": "profile-1"},
            )
            return {
                "providers": [
                    {
                        "provider_instance_id": "provider.adapter-main",
                        "adapter_id": "openai-compatible",
                        "credential_handle": created["handle"],
                        "endpoint": "https://provider.example",
                        "enabled": True,
                    }
                ]
            }

        def provider_metadata(self, _contract_id):
            return ()

    client = GlobalContractClient(
        session=CapturedSession(),
        allowed_contract_ids=frozenset({REGISTRY_CONTRACT}),
        consumer_pack_id="rumi_provider_adapters_pack",
        host_credential_transport=transport,
    )
    result = create_generate_operation(client)(
        "generate",
        {
            "profile_id": "profile-1",
            "provider_id": "adapter-main",
            "model_id": "adapter-main/model",
            "messages": [{"role": "user", "content": "hello"}],
            "deadline": 9_999_999_999.0,
        },
    )

    assert observed_authorization == ["Bearer fixture-secret"]
    assert result["output"] == "[REDACTED] must be redacted"
    public_snapshot = json.dumps(
        {
            "result": result,
            "audit": audit,
            "binding": transport.binding.__dict__,
            "argv": sys.argv,
            "environment": dict(os.environ),
        },
        sort_keys=True,
    )
    assert "fixture-secret" not in public_snapshot
    with pytest.raises(CredentialTransportDenied, match="denied"):
        transport.post_json(
            endpoint="https://provider.example/v1/messages",
            headers={},
            body={},
            credential_handle=created["handle"],
            provider_instance_id="provider.adapter-main",
            credential_scope="ai.generate",
            credential_scheme="bearer",
            deadline=9_999_999_999.0,
        )


def test_revocation_prevents_later_resolution(tmp_path: Path) -> None:
    service = CredentialBrokerService(user_data_root=tmp_path)
    created = service.invoke(
        "create",
        {
            "secret_material": {"token": "fixture"},
            "profile_id": "profile-a",
            "consumer_pack_id": "provider-adapter-pack",
            "provider_instance_id": "adapter-main",
            "scopes": ["generate"],
        },
    )

    service.invoke("revoke", {"handle": created["handle"], "profile_id": "profile-a"})

    with pytest.raises(PermissionError):
        service.invoke(
            "resolve",
            {
                "_contract_consumer_pack_id": "provider-adapter-pack",
                "handle": created["handle"],
                "provider_instance_id": "adapter-main",
                "scope": "generate",
                "profile_id": "profile-a",
            },
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("provider_instance_id", "adapter-other"),
        ("credential_scope", "stream"),
        ("credential_handle", "credential:forged"),
        ("endpoint", "https://other.example/v1/messages"),
    ),
)
def test_host_transport_rejects_wrong_exact_binding(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    service = CredentialBrokerService(user_data_root=tmp_path)
    created = service.invoke(
        "create",
        {
            "secret_material": {"api_key": "binding-sentinel"},
            "profile_id": "profile-1",
            "consumer_pack_id": "provider-adapter-pack",
            "provider_instance_id": "adapter-main",
            "scopes": ["generate"],
        },
    )
    authority, envelope = _dispatched_envelope(tmp_path)
    transport = HostBoundCredentialTransport.from_authorized_envelope(
        envelope,
        provider_principal=authority.target,
        store=service.store,
        authority_store=authority.store,
        credential_handle=created["handle"],
        credential_key_version=created["key_version"],
        provider_instance_id="provider.adapter-main",
        credential_scope="generate",
        credential_purpose="provider.invoke",
        endpoint_origin="https://provider.example",
        current_security_epoch=lambda: authority.store.security_epoch,
        consumer_pack_id="provider-adapter-pack",
    )
    arguments = {
        "endpoint": "https://provider.example/v1/messages",
        "headers": {},
        "body": {},
        "credential_handle": created["handle"],
        "provider_instance_id": "adapter-main",
        "credential_scope": "generate",
        "credential_scheme": "bearer",
        "deadline": 9_999_999_999.0,
    }
    arguments[field] = value
    with pytest.raises(CredentialTransportDenied, match="denied") as denied:
        transport.post_json(**arguments)
    assert "binding-sentinel" not in str(denied.value)


def test_host_transport_rejects_missing_approval_and_revocation(
    tmp_path: Path,
) -> None:
    service = CredentialBrokerService(user_data_root=tmp_path)
    created = service.invoke(
        "create",
        {
            "secret_material": {"api_key": "epoch-sentinel"},
            "profile_id": "profile-1",
            "consumer_pack_id": "provider-adapter-pack",
            "provider_instance_id": "adapter-main",
            "scopes": ["generate"],
        },
    )
    authority, envelope = _dispatched_envelope(tmp_path)
    forged = replace(envelope, lease=type(envelope.lease)(b"forged"))
    with pytest.raises(CredentialTransportDenied, match="denied"):
        HostBoundCredentialTransport.from_authorized_envelope(
            forged,
            provider_principal=authority.target,
            store=service.store,
            authority_store=authority.store,
            credential_handle=created["handle"],
            credential_key_version=created["key_version"],
            provider_instance_id="provider.adapter-main",
            credential_scope="generate",
            credential_purpose="provider.invoke",
            endpoint_origin="https://provider.example",
            current_security_epoch=lambda: authority.store.security_epoch,
        )

    transport = HostBoundCredentialTransport.from_authorized_envelope(
        envelope,
        provider_principal=authority.target,
        store=service.store,
        authority_store=authority.store,
        credential_handle=created["handle"],
        credential_key_version=created["key_version"],
        provider_instance_id="adapter-main",
        credential_scope="generate",
        credential_purpose="provider.invoke",
        endpoint_origin="https://provider.example",
        current_security_epoch=lambda: authority.store.security_epoch,
        consumer_pack_id="provider-adapter-pack",
    )
    authority.kernel.revoke(
        target_kind="function_principal",
        target_id=authority.target.principal_id,
        reason="test credential revoke",
    )
    with pytest.raises(CredentialTransportDenied, match="denied"):
        transport.post_json(
            endpoint="https://provider.example/v1/messages",
            headers={},
            body={},
            credential_handle=created["handle"],
            provider_instance_id="adapter-main",
            credential_scope="generate",
            credential_scheme="bearer",
            deadline=9_999_999_999.0,
        )


def test_credential_migration_is_atomic_redacted_and_reversible(
    tmp_path: Path,
) -> None:
    service = CredentialBrokerService(user_data_root=tmp_path)
    source = {
        "records": [
            {
                "consumer_pack_id": "rumi_provider_adapters_pack",
                "provider_instance_id": "provider.example",
                "scopes": ["ai.generate"],
                "profile_id": "profile-a",
                "secret_material": {"api_key": "not-returned"},
            }
        ]
    }
    raw = json.dumps(source, sort_keys=True, separators=(",", ":")).encode("utf-8")
    result = service.invoke(
        "migration.apply",
        {
            **source,
            "expected_source_hash": "sha256:" + hashlib.sha256(raw).hexdigest(),
        },
    )

    assert result["credentials"][0]["handle"].startswith("credential:")
    assert "not-returned" not in str(result)
    assert service.invoke("migration.rollback", {"migration_id": result["migration_id"]})[
        "rolled_back"
    ]
    assert service.invoke("list", {"profile_id": "profile-a"})["count"] == 0
