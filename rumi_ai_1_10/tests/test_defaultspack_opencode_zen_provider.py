from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def _provider(monkeypatch):
    monkeypatch.setenv("OPENCODE_ZEN_API_KEY", "test-opencode-zen-key")
    from domain.ai_client.providers.opencode_zen_provider import OpencodeZenProvider

    return OpencodeZenProvider()


def test_opencode_zen_catalog_includes_minimax_m3_free():
    from domain.ai_client.providers import get_all_known_models, get_provider_catalog_map

    catalog = get_provider_catalog_map()
    provider = catalog["opencode-zen"]
    models = {item["id"]: item for item in get_all_known_models("opencode-zen")}

    assert provider["metadata"]["adapter"] == "python_entrypoint"
    assert provider["metadata"]["default_base_url"] == "https://opencode.ai/zen"
    assert provider["env_vars"] == ["OPENCODE_ZEN_API_KEY"]
    assert provider["default_model_for"]["coding"] == "minimax-m3-free"
    assert "opencode-zen/minimax-m3-free" in models
    assert models["opencode-zen/minimax-m3-free"]["metadata"]["transport"] == "anthropic_messages"
    assert models["opencode-zen/minimax-m3-free"]["metadata"]["endpoint_path"] == "/v1/messages"


def test_opencode_zen_complete_uses_anthropic_messages(monkeypatch):
    provider = _provider(monkeypatch)
    captured = {}

    def fake_request_json(path, body):
        captured["path"] = path
        captured["body"] = body
        return {
            "id": "msg_test",
            "model": "minimax-m3-free",
            "content": [{"type": "text", "text": "OK"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }

    with patch.object(provider, "_request_json", side_effect=fake_request_json):
        result = provider.complete(
            "opencode/minimax-m3-free",
            [
                {"role": "system", "content": "Be terse."},
                {"role": "user", "content": "Say OK"},
            ],
            [
                {
                    "type": "function",
                    "function": {
                        "name": "noop",
                        "description": "Do nothing",
                        "parameters": {"type": "object"},
                    },
                }
            ],
            {"max_tokens": 8, "temperature": 0},
        )

    assert captured["path"] == "/v1/messages"
    assert captured["body"]["model"] == "minimax-m3-free"
    assert captured["body"]["max_tokens"] == 8
    assert captured["body"]["temperature"] == 0
    assert captured["body"]["system"] == [{"type": "text", "text": "Be terse."}]
    assert captured["body"]["tools"] == [
        {
            "name": "noop",
            "description": "Do nothing",
            "input_schema": {"type": "object"},
        }
    ]
    assert result["content"] == [{"type": "text", "text": "OK"}]


def test_opencode_zen_secret_keys_and_detection(monkeypatch):
    from domain.ai_client.api_key_store import provider_secret_keys
    from domain.ai_client.providers import detect_available_providers
    from domain.ai_client.providers.opencode_zen_provider import OpencodeZenProvider

    assert provider_secret_keys("opencode-zen") == ["OPENCODE_ZEN_API_KEY"]
    monkeypatch.setenv("OPENCODE_ZEN_API_KEY", "test-opencode-zen-key")
    assert isinstance(detect_available_providers()["opencode-zen"], OpencodeZenProvider)


def test_opencode_zen_rejects_unknown_model(monkeypatch):
    provider = _provider(monkeypatch)

    with pytest.raises(RuntimeError, match="unsupported model"):
        provider.complete("opencode-zen/not-a-real-model", [{"role": "user", "content": "hi"}], [], {})


def _live_enabled():
    return os.environ.get("RUMI_OPENCODE_ZEN_LIVE_TEST") == "1" and bool(os.environ.get("OPENCODE_ZEN_API_KEY"))


@pytest.mark.live
@pytest.mark.skipif(not _live_enabled(), reason="set RUMI_OPENCODE_ZEN_LIVE_TEST=1 and OPENCODE_ZEN_API_KEY")
def test_opencode_zen_live_minimax_m3_free_complete():
    from domain.ai_client.providers.opencode_zen_provider import OpencodeZenProvider

    result = OpencodeZenProvider().complete(
        "minimax-m3-free",
        [{"role": "user", "content": "Reply with exactly: OK"}],
        [],
        {"max_tokens": 8},
    )
    assert result["content"]
