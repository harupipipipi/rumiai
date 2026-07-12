from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
DEFAULTSPACK = ROOT / "ecosystem" / "defaultspack"
FIXTURES = ROOT / "tests" / "fixtures" / "provider_tasks"
if str(DEFAULTSPACK) not in sys.path:
    sys.path.insert(0, str(DEFAULTSPACK))

from domain.ai_client.providers import get_provider_catalog_map  # noqa: E402
from domain.ai_client.task_provider_contract import (  # noqa: E402
    PROVIDER_TASK_ENDPOINTS,
    task_models_from_fixture,
    task_request_route,
)
from domain.components.registry import get_domain_component_registry  # noqa: E402


def _fixture(provider_id):
    return json.loads((FIXTURES / f"{provider_id}.json").read_text(encoding="utf-8"))


def _manifest(provider_id):
    payload = json.loads((DEFAULTSPACK / "domain" / "providers" / provider_id / "manifest.json").read_text(encoding="utf-8"))
    return payload["provider_manifest"]


def test_task_provider_matrix_and_fixtures_are_typed_and_current():
    get_domain_component_registry(force_reload=True)
    assert set(PROVIDER_TASK_ENDPOINTS) <= set(get_provider_catalog_map())
    for provider_id, endpoints in PROVIDER_TASK_ENDPOINTS.items():
        fixture = _fixture(provider_id)
        models = task_models_from_fixture(provider_id, fixture)
        assert fixture["verified_at"] == "2026-07-12"
        assert models
        assert {model["type"] for model in models} <= set(endpoints)
        assert all(model["capabilities"]["chat"] is False for model in models)


def test_task_routes_use_provider_specific_endpoints():
    assert task_request_route("elevenlabs", "tts", "eleven_v3", voice_id="voice-1")["path"] == "/v1/text-to-speech/voice-1"
    assert task_request_route("deepgram", "stt", "nova-3")["path"] == "/v1/listen"
    assert task_request_route("stability-ai", "image", "core")["path"] == "/v2beta/stable-image/generate/core"
    assert task_request_route("fal-ai", "video", "fal-ai/wan/v2.2")["path"] == "/fal-ai%2Fwan%2Fv2.2"


def test_task_providers_reject_generic_chat_and_missing_voice():
    with pytest.raises(ValueError, match="not generic chat"):
        task_request_route("deepgram", "chat", "nova-3")
    with pytest.raises(ValueError, match="voice_id"):
        task_request_route("elevenlabs", "tts", "eleven_v3")


def test_task_manifests_are_excluded_from_chat_picker():
    for provider_id in PROVIDER_TASK_ENDPOINTS:
        manifest = _manifest(provider_id)
        assert manifest["config"]["exclude_from_chat_picker"] is True
        assert "default_model" not in manifest
        assert manifest["category"] == "task_provider"
        assert manifest["catalog_only"] is True
        assert manifest["supports_invoke"] is False
