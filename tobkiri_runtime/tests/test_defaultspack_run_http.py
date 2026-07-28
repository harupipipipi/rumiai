from types import SimpleNamespace

import pytest

from ecosystem.defaultspack import run_http


def test_run_http_requires_launcher_owned_user_data(monkeypatch):
    monkeypatch.delenv("RUMI_USER_DATA", raising=False)

    with pytest.raises(RuntimeError, match="Tobkiri Launcher"):
        run_http._require_active_chat_profile()


def test_run_http_requires_one_provider_for_every_chat_contract(
    monkeypatch,
):
    monkeypatch.setenv("RUMI_USER_DATA", "/tmp/tobkiri-test-user-data")
    monkeypatch.setattr(
        "core_runtime.resolved_profile_scope.persisted_resolved_profile",
        lambda: SimpleNamespace(profile_id="test-profile"),
    )
    monkeypatch.setattr(
        "core_runtime.di_container.get_container",
        lambda: SimpleNamespace(get_or_none=lambda _key: object()),
    )
    monkeypatch.setattr(
        "core_runtime.global_contract_dispatch.selected_global_providers",
        lambda _registry, contract_id: (
            ({"contract_id": contract_id},)
            if contract_id != "rumi.resource.message.v1"
            else ()
        ),
    )

    with pytest.raises(RuntimeError, match="no verified conversation owner"):
        run_http._require_active_chat_profile()


def test_run_http_accepts_a_complete_verified_chat_profile(monkeypatch):
    monkeypatch.setenv("RUMI_USER_DATA", "/tmp/tobkiri-test-user-data")
    monkeypatch.setattr(
        "core_runtime.resolved_profile_scope.persisted_resolved_profile",
        lambda: SimpleNamespace(profile_id="test-profile"),
    )
    monkeypatch.setattr(
        "core_runtime.di_container.get_container",
        lambda: SimpleNamespace(get_or_none=lambda _key: object()),
    )
    monkeypatch.setattr(
        "core_runtime.global_contract_dispatch.selected_global_providers",
        lambda _registry, contract_id: ({"contract_id": contract_id},),
    )

    run_http._require_active_chat_profile()
