from __future__ import annotations

from copy import deepcopy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

pytestmark = pytest.mark.contract

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


@pytest.fixture(autouse=True)
def _isolate_runtime_profile_catalog(monkeypatch):
    settings_by_path: dict[str, dict] = {}

    def default_settings() -> dict:
        return {
            "preferred_model": "stub/default",
            "model_groups": [],
            "api_routes": [],
            "api_bound_profiles": [],
        }

    def settings_key(service) -> str:
        return str(getattr(service, "_settings_path", "default"))

    def get_settings(service) -> dict:
        return deepcopy(settings_by_path.setdefault(settings_key(service), default_settings()))

    def update_settings(service, patch: dict) -> dict:
        current = get_settings(service)
        current.update(deepcopy(patch or {}))
        settings_by_path[settings_key(service)] = deepcopy(current)
        return deepcopy(current)

    def runtime_defined_profiles(self, settings=None):
        source = settings if isinstance(settings, dict) else self.get_settings()
        profiles = []
        for item in source.get("api_bound_profiles", []):
            if not isinstance(item, dict):
                continue
            profile = dict(item)
            metadata = dict(profile.get("metadata") or {})
            if profile.get("provider_id"):
                metadata.setdefault("provider_id", profile["provider_id"])
            if profile.get("api_id"):
                metadata.setdefault("api_id", profile["api_id"])
            profile["metadata"] = metadata
            profile.setdefault("availability", {"configured": True, "active": True})
            profiles.append(profile)
        return profiles

    monkeypatch.setattr(
        "domain.ai_client.model_availability.ModelRuntimeSettingsService.get_settings",
        get_settings,
    )
    monkeypatch.setattr(
        "domain.ai_client.model_availability.ModelRuntimeSettingsService.update_settings",
        update_settings,
    )
    monkeypatch.setattr(
        "domain.ai_client.model_availability.ModelRuntimeSettingsService.runtime_defined_profiles",
        runtime_defined_profiles,
    )
    monkeypatch.setattr(
        "domain.ai_client.model_availability.ModelAvailabilityService._candidate_models",
        lambda self, provider_id: [],
    )


def test_provider_key_save_with_default_model_creates_available_api_bound_profile(tmp_path):
    from domain.ai_client.api_key_store import set_provider_api_key
    from domain.ai_client.model_availability import ModelAvailabilityService

    result = set_provider_api_key(
        "examplellm",
        "secret",
        pack_root=tmp_path,
        api_id="main",
        name="main",
        default_model="example-chat",
    )
    assert result["success"] is True

    availability = ModelAvailabilityService(tmp_path).after_provider_key_saved(
        "examplellm",
        "main",
        default_model="example-chat",
    )

    assert availability["status"] == "models_available"
    assert availability["selected_profile_id"] == "examplellm/main/example-chat"
    assert availability["profiles"][0]["availability"]["configured"] is True


def test_provider_key_save_without_model_binding_requires_explicit_route(tmp_path):
    from domain.ai_client.api_key_store import set_provider_api_key
    from domain.ai_client.model_availability import ModelAvailabilityService

    result = set_provider_api_key(
        "examplellm",
        "secret",
        pack_root=tmp_path,
        api_id="main",
        name="main",
    )
    assert result["success"] is True

    availability = ModelAvailabilityService(tmp_path).after_provider_key_saved("examplellm", "main")

    assert availability["status"] == "route_required"
    assert availability["provider_id"] == "examplellm"
    assert availability["api_id"] == "main"
    assert "Choose a default model" in availability["reason"]


def test_provider_key_block_response_includes_model_availability(tmp_path, monkeypatch):
    from blocks.ai import provider_key
    from domain.ai_client.model_availability import ModelAvailabilityService

    monkeypatch.setenv("RUMI_DEFAULTSPACK_SECRETS_DIR", str(tmp_path / "secrets"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    class TempModelAvailabilityService(ModelAvailabilityService):
        def __init__(self):
            super().__init__(tmp_path)

    monkeypatch.setattr(provider_key, "ModelAvailabilityService", TempModelAvailabilityService)

    response = provider_key.run(
        {
            "_method": "POST",
            "provider_id": "openai",
            "api_id": "main",
            "name": "main",
            "value": "sk-test",
            "default_model": "gpt-test",
        },
        {},
    )

    assert response["status"] == "ok"
    availability = response["data"]["model_availability"]
    assert availability["status"] == "models_available"
    assert availability["selected_profile_id"] == "openai/main/gpt-test"


def test_provider_key_block_response_warns_when_route_is_required(tmp_path, monkeypatch):
    from blocks.ai import provider_key
    from domain.ai_client.model_availability import ModelAvailabilityService

    monkeypatch.setenv("RUMI_DEFAULTSPACK_SECRETS_DIR", str(tmp_path / "secrets"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    class TempModelAvailabilityService(ModelAvailabilityService):
        def __init__(self):
            super().__init__(tmp_path)

    monkeypatch.setattr(provider_key, "ModelAvailabilityService", TempModelAvailabilityService)

    response = provider_key.run(
        {
            "_method": "POST",
            "provider_id": "openai",
            "api_id": "main",
            "name": "main",
            "value": "sk-test",
        },
        {},
    )

    assert response["status"] == "ok"
    availability = response["data"]["model_availability"]
    assert availability["status"] == "route_required"
    assert availability["provider_id"] == "openai"
    assert availability["api_id"] == "main"
