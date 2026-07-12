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

from domain.ai_client.providers import (  # noqa: E402
    get_all_known_models,
    get_provider_catalog_map,
)
from domain.ai_client.task_provider_contract import (  # noqa: E402
    PROVIDER_TASK_ENDPOINTS,
    task_models_from_fixture,
    task_request_route,
)
from domain.ai_client.task_provider_runtime import (  # noqa: E402
    TaskProviderAdapter,
    TaskProviderError,
    list_task_model_catalog,
    load_task_provider_adapter,
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
        assert {model["metadata"]["task"] for model in models} <= set(endpoints)
        assert all(model["capabilities"]["chat"] is False for model in models)


def test_task_routes_use_provider_specific_endpoints():
    assert task_request_route("elevenlabs", "tts", "eleven_v3", voice_id="voice-1")["path"] == "/v1/text-to-speech/voice-1"
    assert task_request_route("deepgram", "stt", "nova-3")["path"] == "/v1/listen"
    assert task_request_route("stability-ai", "image", "core")["path"] == "/v2beta/stable-image/generate/core"
    assert task_request_route("fal-ai", "video", "fal-ai/wan/v2.2")["path"] == "/fal-ai/wan/v2.2"


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
        assert manifest["catalog_only"] is False
        assert manifest["supports_invoke"] is True


def test_task_snapshots_feed_the_unified_catalog_with_non_chat_types():
    get_domain_component_registry(force_reload=True)
    provider_ids = set(PROVIDER_TASK_ENDPOINTS)
    models = [
        model
        for model in get_all_known_models()
        if model.get("provider_id") in provider_ids
    ]
    assert len(models) == 15
    assert {model["type"] for model in models} == {
        "transcription",
        "tts",
        "music",
        "image",
        "video",
    }
    assert all(model["type"] != "chat" for model in models)
    assert all(model["supports_invoke"] is True for model in models)

    image_picker = list_task_model_catalog("image", root=ROOT)
    assert {model["provider_id"] for model in image_picker} == {
        "black-forest-labs",
        "fal-ai",
        "stability-ai",
    }
    assert all(model["metadata"]["task"] == "image" for model in image_picker)


class _Response:
    def __init__(self, payload, content_type="application/json"):
        self._payload = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.status = 200
        self.headers = {"Content-Type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self._payload


def _adapter(provider_id, *, opener=lambda *_args, **_kwargs: None):
    return TaskProviderAdapter(
        _manifest(provider_id),
        _fixture(provider_id),
        api_key="not-a-real-key",
        opener=opener,
    )


def test_native_adapters_compile_official_auth_and_payload_shapes():
    eleven = _adapter("elevenlabs")
    request = eleven.build_request(
        "tts", "eleven_v3", {"text": "hello"}, voice_id="voice-1"
    )
    assert request.url.endswith("/v1/text-to-speech/voice-1")
    assert request.headers["xi-api-key"] == "not-a-real-key"
    assert json.loads(request.body) == {"text": "hello", "model_id": "eleven_v3"}

    deepgram = _adapter("deepgram")
    request = deepgram.build_request("stt", "nova-3", {"url": "https://example.test/a.wav"})
    assert request.url.endswith("/v1/listen?model=nova-3")
    assert request.headers["Authorization"] == "Token not-a-real-key"

    assembly = _adapter("assemblyai")
    request = assembly.build_request(
        "stt", "universal-3-pro", {"audio_url": "https://example.test/a.wav"}
    )
    assert json.loads(request.body)["speech_model"] == "universal-3-pro"
    assert request.headers["Authorization"] == "not-a-real-key"

    stability = _adapter("stability-ai")
    request = stability.build_request("image", "core", {"prompt": "a lighthouse"})
    assert request.url.endswith("/v2beta/stable-image/generate/core")
    assert request.headers["Authorization"] == "Bearer not-a-real-key"
    assert b"a lighthouse" in request.body

    bfl = _adapter("black-forest-labs")
    request = bfl.build_request("image", "flux-pro-1.1", {"prompt": "mountains"})
    assert request.headers["x-key"] == "not-a-real-key"

    fal = _adapter("fal-ai")
    request = fal.build_request("video", "fal-ai/wan/v2.2-a14b/text-to-video", {"prompt": "waves"})
    assert request.url.endswith("/fal-ai/wan/v2.2-a14b/text-to-video")
    assert request.headers["Authorization"] == "Key not-a-real-key"


def test_native_model_inventory_is_typed_without_chat_fallback():
    payload = {
        "stt": [{"canonical_name": "nova-3", "name": "Nova 3", "streaming": True}],
        "tts": [{"canonical_name": "aura-2-zeus-en", "name": "Zeus"}],
    }
    adapter = _adapter("deepgram", opener=lambda *_args, **_kwargs: _Response(payload))
    models = adapter.list_models(refresh=True)
    assert {model["type"] for model in models} == {"transcription", "tts"}
    assert all(model["capabilities"]["chat"] is False for model in models)
    assert {model["model_id"] for model in models} == {"nova-3", "aura-2-zeus-en"}


def test_invoke_normalizes_json_and_binary_responses():
    json_adapter = _adapter(
        "assemblyai", opener=lambda *_args, **_kwargs: _Response({"id": "transcript-1"})
    )
    result = json_adapter.invoke(
        "stt", "universal-3-pro", {"audio_url": "https://example.test/a.wav"}
    )
    assert result["data"] == {"id": "transcript-1"}

    audio_adapter = _adapter(
        "elevenlabs",
        opener=lambda *_args, **_kwargs: _Response(b"audio", "audio/mpeg"),
    )
    result = audio_adapter.invoke(
        "tts", "eleven_v3", {"text": "hello"}, voice_id="voice-1"
    )
    assert result["data"] == b"audio"
    assert result["content_type"] == "audio/mpeg"


def test_fixture_loader_and_missing_credentials_fail_closed(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    adapter = load_task_provider_adapter(_manifest("elevenlabs"), root=ROOT)
    with pytest.raises(TaskProviderError) as failure:
        adapter.build_request("tts", "eleven_v3", {"text": "hello"}, voice_id="voice-1")
    assert failure.value.code == "authentication_required"
