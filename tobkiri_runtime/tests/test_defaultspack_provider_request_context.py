from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import sys
from pathlib import Path

import pytest

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parent.parent
        / "ecosystem"
        / "defaultspack"
    ),
)

from domain.ai_client.base_provider import BaseProvider
from domain.ai_client.api_key_store import set_provider_api_key
from domain.ai_client.client import AIClient
from domain.ai_client.provider_endpoint import (
    normalize_provider_base_url,
    provider_endpoint_url,
)
from domain.ai_client.provider_error import ProviderError
from domain.ai_client.provider_identity import (
    canonical_model_ref,
    canonical_provider_id,
    provider_id_aliases,
)
from domain.ai_client.providers.anthropic_provider import AnthropicProvider
from domain.ai_client.providers.openai_provider import OpenAIProvider
from domain.ai_client.providers.openrouter_provider import OpenRouterProvider


class _CapturingProvider(BaseProvider):
    def __init__(self) -> None:
        self._api_key = "registry-key"
        self._base_url = "https://registry.example/v1"
        self.BASE_URL = self._base_url
        self.barrier = threading.Barrier(2)

    def complete(self, model, messages, tools, params):
        del model, messages, tools, params
        self.barrier.wait(timeout=5)
        return self._api_key, self.BASE_URL

    def stream(self, model, messages, tools, params):
        del model, messages, tools, params
        self.barrier.wait(timeout=5)
        yield self._api_key, self.BASE_URL


def _call(client, provider, key, url):
    return client._call_provider_with_overrides(
        provider,
        "model",
        key,
        {"base_url": url},
        "complete",
        [],
        [],
        {},
    )


def test_named_api_overrides_are_request_scoped_under_concurrency():
    client = object.__new__(AIClient)
    provider = _CapturingProvider()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(
            _call,
            client,
            provider,
            "first-key",
            "https://first.example/v1/",
        )
        second = executor.submit(
            _call,
            client,
            provider,
            "second-key",
            "https://second.example/v1",
        )

    assert {first.result(), second.result()} == {
        ("first-key", "https://first.example/v1"),
        ("second-key", "https://second.example/v1"),
    }
    assert provider._api_key == "registry-key"
    assert provider.BASE_URL == "https://registry.example/v1"


def test_named_api_stream_overrides_do_not_mutate_registry_provider():
    client = object.__new__(AIClient)
    provider = _CapturingProvider()
    attempts = [
        (provider, "model", "first-key", {"base_url": "https://first.example/v1"}),
        (provider, "model", "second-key", {"base_url": "https://second.example/v1"}),
    ]

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                lambda attempt=attempt: list(
                    client._stream_with_api_routes([attempt], [], [], {})
                )
            )
            for attempt in attempts
        ]

    assert {tuple(future.result()[0]) for future in futures} == {
        ("first-key", "https://first.example/v1"),
        ("second-key", "https://second.example/v1"),
    }
    assert provider._api_key == "registry-key"
    assert provider.BASE_URL == "https://registry.example/v1"


def test_four_parallel_named_api_routes_remain_isolated():
    client = object.__new__(AIClient)
    provider = _CapturingProvider()
    provider.barrier = threading.Barrier(4)
    expected = {
        (f"key-{index}", f"https://route-{index}.example/v1")
        for index in range(4)
    }

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(
                _call,
                client,
                provider,
                f"key-{index}",
                f"https://route-{index}.example/v1",
            )
            for index in range(4)
        ]

    assert {future.result() for future in futures} == expected
    assert provider._api_key == "registry-key"
    assert provider.BASE_URL == "https://registry.example/v1"


@pytest.mark.parametrize(
    "value",
    [
        "ftp://provider.example/v1",
        "https://user:secret@provider.example/v1",
        "https://provider.example/v1?token=secret",
        "https://provider.example/v1#fragment",
        "https://provider.example/v1/chat/completions",
        "https://provider.example/v1/models",
    ],
)
def test_provider_base_url_rejects_non_root_or_ambiguous_values(value):
    with pytest.raises(ValueError):
        normalize_provider_base_url(value)


def test_provider_endpoint_normalizes_slashes_without_guessing_api_version():
    assert normalize_provider_base_url("HTTPS://Provider.Example//custom//v2/") == (
        "https://provider.example/custom/v2"
    )
    assert provider_endpoint_url("https://provider.example/custom/v2/", "/models") == (
        "https://provider.example/custom/v2/models"
    )
    assert normalize_provider_base_url("http://[::1]:8080/v1/") == (
        "http://[::1]:8080/v1"
    )


def test_named_api_rejects_operation_url_before_persisting(tmp_path):
    result = set_provider_api_key(
        "openai",
        "secret",
        pack_root=tmp_path,
        api_id="unsafe",
        base_url="https://provider.example/v1/chat/completions",
    )

    assert result["success"] is False
    assert "API root" in result["error"]


def test_native_providers_honor_base_url_environment(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://openai-proxy.example/custom/v2/")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://anthropic-proxy.example/root/")

    assert OpenAIProvider().BASE_URL == "https://openai-proxy.example/custom/v2"
    assert AnthropicProvider().BASE_URL == "https://anthropic-proxy.example/root"


def test_openai_final_url_and_auth_reach_local_contract_server(monkeypatch):
    captured = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            captured["path"] = self.path
            captured["authorization"] = self.headers.get("Authorization")
            captured["body"] = json.loads(self.rfile.read(length))
            payload = json.dumps(
                {
                    "choices": [
                        {
                            "message": {"content": "ok"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {},
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, _format, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        monkeypatch.setenv(
            "OPENAI_BASE_URL",
            f"http://127.0.0.1:{server.server_port}/custom/v1/",
        )
        monkeypatch.setenv("OPENAI_API_KEY", "contract-key")
        response = OpenAIProvider().complete(
            "account-model",
            [{"role": "user", "content": "hello"}],
            [],
            {},
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert response["content"][0]["text"] == "ok"
    assert captured == {
        "path": "/custom/v1/chat/completions",
        "authorization": "Bearer contract-key",
        "body": {
            "model": "account-model",
            "messages": [{"role": "user", "content": "hello"}],
        },
    }


class _HttpError:
    def __init__(self, status, headers=None):
        self.code = status
        self.headers = headers or {}


def test_provider_error_keeps_structured_retry_metadata():
    error = ProviderError.from_http_error(
        "openrouter",
        _HttpError(429, {"Retry-After": "7", "x-request-id": "req_123"}),
        '{"error":{"code":"rate_limit_exceeded","message":"Slow down"}}',
    )

    assert error.kind == "rate_limit"
    assert error.http_status == 429
    assert error.provider_code == "rate_limit_exceeded"
    assert error.retry_after == "7"
    assert error.request_id == "req_123"
    assert error.fallback_eligible is True
    assert AIClient._error_kind(error) == "rate_limit"


def test_credit_errors_are_not_fallback_eligible():
    error = ProviderError.from_http_error(
        "openrouter",
        _HttpError(402),
        '{"error":{"code":"insufficient_credit","message":"Credit balance is empty"}}',
    )

    assert error.kind == "payment_required"
    assert error.fallback_eligible is False
    assert AIClient._is_rate_limit_error(error) is False


@pytest.mark.parametrize(
    ("status", "kind"),
    [
        (400, "invalid_request"),
        (401, "unauthorized"),
        (402, "payment_required"),
        (403, "forbidden"),
        (404, "not_found"),
        (408, "timeout"),
        (409, "conflict"),
        (422, "invalid_request"),
        (429, "rate_limit"),
        (500, "provider_error"),
        (504, "provider_error"),
    ],
)
def test_provider_error_classifies_http_status_without_message_search(status, kind):
    error = ProviderError.from_http_error("provider", _HttpError(status), "{}")

    assert error.http_status == status
    assert error.kind == kind


def test_openrouter_uses_tobkiri_identity_headers(monkeypatch):
    monkeypatch.delenv("OPENROUTER_HTTP_REFERER", raising=False)
    monkeypatch.delenv("OPENROUTER_X_TITLE", raising=False)
    monkeypatch.delenv("OPENROUTER_X_OPENROUTER_TITLE", raising=False)

    provider = OpenRouterProvider(known_models=[])

    assert provider._extra_headers["HTTP-Referer"] == (
        "https://github.com/harupipipipi/tobkiri"
    )
    assert provider._extra_headers["X-Title"] == "tobkiri-defaultspack"


def test_openrouter_rejects_header_injection(monkeypatch):
    monkeypatch.setenv("OPENROUTER_X_TITLE", "Tobkiri\r\nX-Evil: injected")

    with pytest.raises(ValueError, match="newlines"):
        OpenRouterProvider(known_models=[])


class _ChunkedResponse:
    def __init__(self, chunks):
        self._chunks = iter(chunks)
        self.closed = False

    def read(self, _size):
        return next(self._chunks, b"")

    def close(self):
        self.closed = True


def test_openai_sse_accepts_crlf_multiline_and_usage_only_final(monkeypatch):
    provider = OpenAIProvider()
    response = _ChunkedResponse(
        [
            b'data: {"choices":[{"delta":{"content":"OK"},\r\n',
            b'data: "finish_reason":"stop"}]}\r\n\r\n',
            b'data:{"choices":[],"usage":{"prompt_tokens":2,'
            b'"completion_tokens":1,"total_tokens":3}}\r\n\r\n',
            b"data: [DONE]\r\n\r\n",
        ]
    )
    monkeypatch.setattr(provider, "_request_stream", lambda *_args, **_kwargs: response)

    events = list(provider.stream("gpt-test", [], [], {}))

    assert events[0] == {
        "type": "content_delta",
        "delta": {"type": "text", "text": "OK"},
    }
    assert events[-1] == {
        "type": "stream_end",
        "finish_reason": "stop",
        "usage": {"input_tokens": 2, "output_tokens": 1, "total_tokens": 3},
    }
    assert response.closed is True


def test_anthropic_stream_normalizes_thinking_delta(monkeypatch):
    provider = AnthropicProvider()
    response = _ChunkedResponse(
        [
            b'event: message_start\ndata: {"message":{"usage":{"input_tokens":2}}}\n\n'
            b'event: content_block_delta\ndata: {"delta":{"type":"thinking_delta",'
            b'"thinking":"Reasoning"}}\n\n'
            b'event: message_delta\ndata: {"delta":{"stop_reason":"end_turn"},'
            b'"usage":{"output_tokens":1}}\n\n',
        ]
    )
    monkeypatch.setattr(provider, "_request_stream", lambda *_args, **_kwargs: response)

    events = list(provider.stream("claude-test", [], [], {}))

    assert events[0] == {
        "type": "reasoning_delta",
        "delta": {"type": "text", "text": "Reasoning"},
    }
    assert events[-1]["usage"] == {
        "input_tokens": 2,
        "output_tokens": 1,
        "total_tokens": 3,
    }


def test_provider_registration_error_remains_visible_in_catalog(monkeypatch):
    from domain.ai_client import providers

    manifest = {
        "id": "broken-provider",
        "display_name": "Broken Provider",
        "credential_required": False,
        "default_base_url": "https://broken.example/v1",
        "supports_invoke": True,
    }
    monkeypatch.setattr(providers, "_PROVIDER_RUNTIME_DIAGNOSTICS", {})
    monkeypatch.setattr(providers, "load_provider_api_keys_into_env", lambda: None)
    monkeypatch.setattr(
        providers,
        "_provider_manifest_map",
        lambda: {"broken-provider": manifest},
    )
    monkeypatch.setattr(providers, "_credentials_ready", lambda *_args: True)
    monkeypatch.setattr(
        providers,
        "_instantiate_manifest_provider",
        lambda _manifest: (_ for _ in ()).throw(ImportError("missing adapter")),
    )
    monkeypatch.setattr(providers, "_load_legacy_providers", lambda: {})

    assert providers.detect_available_providers() == {}
    diagnostic = providers.get_provider_runtime_diagnostics()["broken-provider"]
    catalog = providers.get_provider_catalog_map()["broken-provider"]

    assert diagnostic["kind"] == "registration_error"
    assert diagnostic["error_type"] == "ImportError"
    assert catalog["availability"]["status"] == "registration_error"
    assert catalog["metadata"]["runtime_diagnostic"] == diagnostic


def test_model_sync_error_is_retained_for_provider_health(monkeypatch):
    from domain.ai_client import providers
    from domain.ai_client.providers.openai_compatible_provider import (
        OpenAICompatibleProvider,
    )

    provider = OpenAICompatibleProvider(
        provider_id="broken-models",
        api_key="key",
        base_url="https://models.example/v1",
        remote_model_discovery=True,
    )
    monkeypatch.setattr(provider, "_load_remote_model_cache", lambda: None)
    monkeypatch.setattr(
        provider,
        "_fetch_remote_models",
        lambda: (_ for _ in ()).throw(ValueError("invalid model response")),
    )
    monkeypatch.setattr(providers, "_PROVIDER_RUNTIME_DIAGNOSTICS", {})
    client = object.__new__(AIClient)
    client._providers = {"broken-models": provider}

    assert client._provider_model_candidates("broken-models") == []
    diagnostic = providers.get_provider_runtime_diagnostics()["broken-models"]
    assert diagnostic["kind"] == "model_sync_error"
    assert diagnostic["error_type"] == "ValueError"
    assert "invalid model response" in diagnostic["message"]


def test_provider_aliases_resolve_to_catalog_canonical_ids():
    assert canonical_provider_id("llama_cpp") == "llamacpp"
    assert canonical_provider_id("lm-studio") == "lmstudio"
    assert canonical_provider_id("gemini") == "google"
    assert canonical_model_ref("llama_cpp/local-gguf") == "llamacpp/local-gguf"
    assert "llama_cpp" in provider_id_aliases("llamacpp")


def test_api_key_save_migrates_legacy_provider_alias(tmp_path):
    result = set_provider_api_key(
        "llama_cpp",
        "local-secret",
        pack_root=tmp_path,
        api_id="main",
        base_url="http://127.0.0.1:8080/v1",
    )

    assert result["success"] is True
    assert result["provider_id"] == "llamacpp"
    assert result["key"].startswith("RUMIAPI_LLAMACPP_")


def test_executable_provider_descriptors_generate_secret_mapping():
    from domain.ai_client.api_key_store import PROVIDER_SECRET_KEYS
    from domain.ai_client.providers import _provider_manifest_map

    missing = []
    for provider_id, descriptor in _provider_manifest_map().items():
        if not descriptor.get("supports_invoke", True):
            continue
        if not descriptor.get("credential_required", True):
            continue
        if provider_id == "aws-bedrock":
            # Bedrock uses one structured named credential so access key,
            # secret key, and optional session token stay atomic.
            continue
        if not PROVIDER_SECRET_KEYS.get(provider_id):
            missing.append(provider_id)

    assert missing == []
