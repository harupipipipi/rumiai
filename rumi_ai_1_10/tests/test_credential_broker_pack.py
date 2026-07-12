from __future__ import annotations

from pathlib import Path

import pytest

from ecosystem.rumi_credential_broker_pack.runtime.service import (
    CredentialBrokerService,
)


def test_credential_material_is_encrypted_and_listing_is_redacted(
    tmp_path: Path,
) -> None:
    service = CredentialBrokerService(user_data_root=tmp_path)

    created = service.invoke(
        "create",
        {
            "secret_material": {"api_key": "fixture-secret"},
            "consumer_pack_id": "provider-adapter-pack",
            "provider_instance_id": "adapter-main",
            "scopes": ["generate", "stream"],
            "label": "fixture",
        },
    )
    listed = service.invoke("list", {})

    store_text = service.store.path.read_text(encoding="utf-8")
    assert "fixture-secret" not in store_text
    assert "ciphertext" not in str(listed)
    assert "secret_material" not in str(listed)
    assert created["handle"].startswith("credential:")


def test_resolution_binds_manifest_consumer_provider_and_scope(
    tmp_path: Path,
) -> None:
    service = CredentialBrokerService(user_data_root=tmp_path)
    created = service.invoke(
        "create",
        {
            "secret_material": {"api_key": "fixture-secret"},
            "consumer_pack_id": "provider-adapter-pack",
            "provider_instance_id": "adapter-main",
            "scopes": ["generate"],
        },
    )

    resolved = service.invoke(
        "resolve",
        {
            "_contract_consumer_pack_id": "provider-adapter-pack",
            "handle": created["handle"],
            "provider_instance_id": "adapter-main",
            "scope": "generate",
        },
    )

    assert resolved == {"secret_material": {"api_key": "fixture-secret"}}
    for patch in (
        {"_contract_consumer_pack_id": "foreign-pack"},
        {"provider_instance_id": "adapter-other"},
        {"scope": "stream"},
    ):
        payload = {
            "_contract_consumer_pack_id": "provider-adapter-pack",
            "handle": created["handle"],
            "provider_instance_id": "adapter-main",
            "scope": "generate",
            **patch,
        }
        with pytest.raises(PermissionError):
            service.invoke("resolve", payload)


def test_revocation_prevents_later_resolution(tmp_path: Path) -> None:
    service = CredentialBrokerService(user_data_root=tmp_path)
    created = service.invoke(
        "create",
        {
            "secret_material": {"token": "fixture"},
            "consumer_pack_id": "provider-adapter-pack",
            "provider_instance_id": "adapter-main",
            "scopes": ["generate"],
        },
    )

    service.invoke("revoke", {"handle": created["handle"]})

    with pytest.raises(KeyError):
        service.invoke(
            "resolve",
            {
                "_contract_consumer_pack_id": "provider-adapter-pack",
                "handle": created["handle"],
                "provider_instance_id": "adapter-main",
                "scope": "generate",
            },
        )
