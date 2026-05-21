from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


OPENGATEWAY_MODELS = {
    "gitlawb-opengateway/mimo-v2.5-pro",
    "gitlawb-opengateway/mimo-v2-flash",
    "gitlawb-opengateway/mimo-v2-omni",
    "gitlawb-opengateway/mimo-v2-pro",
    "gitlawb-opengateway/mimo-v2.5",
}


def _reset_client():
    from domain.ai_client.client import AIClient

    AIClient._instance = None


def test_get_all_known_models_includes_exact_opengateway_allowlist():
    from domain.ai_client.providers import get_all_known_models

    model_ids = {item["id"] for item in get_all_known_models()}
    opengateway_ids = {item for item in model_ids if item.startswith("gitlawb-opengateway/")}

    assert opengateway_ids == OPENGATEWAY_MODELS


def test_provider_catalog_includes_opengateway():
    from domain.ai_client.providers import get_provider_catalog_map

    catalog = get_provider_catalog_map()

    provider = catalog["gitlawb-opengateway"]
    assert provider["provider_id"] == "gitlawb-opengateway"
    assert provider["env_vars"] == ["GITLAWB_OPENGATEWAY_API_KEY"]
    assert provider["base_url_envs"] == ["GITLAWB_OPENGATEWAY_BASE_URL"]
    assert provider["metadata"]["default_base_url"] == "https://opengateway.gitlawb.com/v1"
    assert provider["availability"]["base_url_hint"] == "https://opengateway.gitlawb.com/v1"


def test_opengateway_not_auto_registered_without_cloud_opt_in():
    from domain.ai_client.client import AIClient

    _reset_client()
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict(
            os.environ,
            {"RUMI_DEFAULTSPACK_SECRETS_DIR": str(Path(tmpdir) / "secrets")},
            clear=True,
        ):
            client = AIClient()
            try:
                assert "gitlawb-opengateway" not in client._providers
            finally:
                _reset_client()


def test_opengateway_auto_registered_with_cloud_opt_in():
    from domain.ai_client.client import AIClient

    _reset_client()
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict(
            os.environ,
            {
                "RUMI_DEFAULTSPACK_ENABLE_CLOUD_PROVIDERS": "1",
                "RUMI_DEFAULTSPACK_SECRETS_DIR": str(Path(tmpdir) / "secrets"),
            },
            clear=True,
        ):
            client = AIClient()
            try:
                assert "gitlawb-opengateway" in client._providers
            finally:
                _reset_client()


@pytest.mark.parametrize(
    ("model_ref", "model_id"),
    [
        ("gitlawb-opengateway/mimo-v2.5-pro", "mimo-v2.5-pro"),
        ("gitlawb-opengateway/mimo-v2-flash", "mimo-v2-flash"),
        ("gitlawb-opengateway/mimo-v2-pro", "mimo-v2-pro"),
        ("gitlawb-opengateway/mimo-v2.5", "mimo-v2.5"),
    ],
)
def test_opengateway_resolve_provider(model_ref, model_id):
    from domain.ai_client.client import AIClient

    _reset_client()
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict(
            os.environ,
            {
                "RUMI_DEFAULTSPACK_ENABLE_CLOUD_PROVIDERS": "1",
                "RUMI_DEFAULTSPACK_SECRETS_DIR": str(Path(tmpdir) / "secrets"),
            },
            clear=True,
        ):
            client = AIClient()
            try:
                provider, resolved_model = client.resolve_provider(model_ref)
            finally:
                _reset_client()

    assert getattr(provider, "provider_id", "") == "gitlawb-opengateway"
    assert resolved_model == model_id


def test_opengateway_list_models_returns_only_allowlist():
    from domain.ai_client.providers.gitlawb_opengateway_provider import (
        GitlawbOpengatewayProvider,
    )

    provider = GitlawbOpengatewayProvider()

    assert {item["id"] for item in provider.list_models()} == OPENGATEWAY_MODELS


def test_opengateway_omni_declares_verified_vision():
    from domain.ai_client.providers.gitlawb_opengateway_provider import (
        GitlawbOpengatewayProvider,
    )

    provider = GitlawbOpengatewayProvider()
    profiles = {item["id"]: item for item in provider.list_models()}
    omni = profiles["gitlawb-opengateway/mimo-v2-omni"]

    assert "vision" in omni["capabilities"]
    assert omni["metadata"]["vision_verified"] is True


def test_opengateway_rejects_non_allowlisted_models():
    from domain.ai_client.providers.gitlawb_opengateway_provider import (
        GitlawbOpengatewayProvider,
    )

    provider = GitlawbOpengatewayProvider()

    with pytest.raises(RuntimeError, match="unsupported model"):
        provider.complete("openai/gpt-4o", [{"role": "user", "content": "hi"}], [], {})


def test_opengateway_translates_max_tokens_to_max_completion_tokens():
    from domain.ai_client.providers.gitlawb_opengateway_provider import (
        GitlawbOpengatewayProvider,
    )

    captured = {}
    provider = GitlawbOpengatewayProvider()

    def fake_request_json(path, body):
        captured["path"] = path
        captured["body"] = body
        return {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}

    with patch.object(provider, "_request_json", side_effect=fake_request_json):
        provider.complete(
            "mimo-v2.5-pro",
            [{"role": "user", "content": "hi"}],
            [],
            {"max_tokens": 17, "temperature": 0.2},
        )

    assert captured["path"] == "/chat/completions"
    assert "max_tokens" not in captured["body"]
    assert captured["body"]["max_completion_tokens"] == 17
    assert captured["body"]["temperature"] == 0.2


def test_opengateway_keeps_existing_max_completion_tokens():
    from domain.ai_client.providers.gitlawb_opengateway_provider import (
        GitlawbOpengatewayProvider,
    )

    captured = {}
    provider = GitlawbOpengatewayProvider()

    def fake_request_json(path, body):
        captured["body"] = body
        return {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}

    with patch.object(provider, "_request_json", side_effect=fake_request_json):
        provider.complete(
            "mimo-v2.5-pro",
            [{"role": "user", "content": "hi"}],
            [],
            {"max_tokens": 17, "max_completion_tokens": 23},
        )

    assert captured["body"]["max_tokens"] == 17
    assert captured["body"]["max_completion_tokens"] == 23


def test_max_tokens_translation_is_scoped_to_opengateway():
    from domain.ai_client.providers.openai_compatible_provider import (
        OpenAICompatibleProvider,
    )

    translated = OpenAICompatibleProvider._translate_params({"max_tokens": 17})

    assert translated == {"max_tokens": 17}


def test_opengateway_credential_required_false_allows_no_api_key():
    from domain.ai_client.providers.gitlawb_opengateway_provider import (
        GitlawbOpengatewayProvider,
    )

    with patch.dict(os.environ, {}, clear=True):
        provider = GitlawbOpengatewayProvider()
        provider._ensure_runtime_config()

    assert provider._credential_required is False
    assert provider._headers()["Authorization"] == "Bearer anything"


def test_opengateway_optional_token_overrides_no_key_fallback():
    from domain.ai_client.providers.gitlawb_opengateway_provider import (
        GitlawbOpengatewayProvider,
    )

    with patch.dict(os.environ, {"GITLAWB_OPENGATEWAY_API_KEY": "test-gb-token"}, clear=True):
        provider = GitlawbOpengatewayProvider()

    assert provider._credential_required is False
    assert provider._headers()["Authorization"] == "Bearer test-gb-token"


def test_opengateway_api_key_can_be_saved_as_defaultspack_secret():
    from core_runtime.secrets_store import SecretsStore
    from domain.ai_client.api_key_store import (
        load_provider_api_keys_into_env,
        provider_has_api_key,
        provider_secret_keys,
        set_provider_api_key,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        secrets_dir = Path(tmpdir) / "secrets"
        with patch.dict(os.environ, {"RUMI_DEFAULTSPACK_SECRETS_DIR": str(secrets_dir)}, clear=True):
            result = set_provider_api_key("gitlawb-opengateway", "test-gb-token")
            store = SecretsStore(str(secrets_dir))

            assert result["success"] is True
            assert provider_secret_keys("gitlawb-opengateway") == ["GITLAWB_OPENGATEWAY_API_KEY"]
            assert provider_has_api_key("gitlawb-opengateway") is True
            assert store.has_secret("GITLAWB_OPENGATEWAY_API_KEY") is True
            loaded = load_provider_api_keys_into_env()
            assert loaded["gitlawb-opengateway"] is True
            assert os.environ["GITLAWB_OPENGATEWAY_API_KEY"] == "test-gb-token"


def test_opengateway_uses_browser_user_agent_for_gateway_compatibility():
    from domain.ai_client.providers.gitlawb_opengateway_provider import (
        GitlawbOpengatewayProvider,
    )

    provider = GitlawbOpengatewayProvider()

    assert provider._headers()["User-Agent"].startswith("Mozilla/5.0")
