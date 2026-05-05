from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def _key_env(monkeypatch, tmp_path):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_API_KEYS_PATH", str(tmp_path / "shared" / "api_keys" / "keys.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_SECRETS_DIR", str(tmp_path / "secrets"))


def test_named_key_metadata_is_redacted_and_resolver_precedence(monkeypatch, tmp_path):
    from domain.ai_client.key_manager import KeyManager
    from domain.ai_client.key_resolver import KeyResolver

    _key_env(monkeypatch, tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    manager = KeyManager()

    manager.create_key(
        provider_id="openai",
        value="sk-provider-secret",
        key_id="provider",
        env_var="OPENAI_API_KEY",
        default_for_provider=True,
    )
    manager.create_key(
        provider_id="openai",
        value="sk-profile-secret",
        key_id="profile",
        env_var="OPENAI_API_KEY",
        profile_ids=["writer"],
    )
    manager.create_key(
        provider_id="openai",
        value="sk-agent-secret",
        key_id="agent",
        env_var="OPENAI_API_KEY",
        agent_ids=["agent-1"],
    )
    manager.create_key(
        provider_id="openai",
        value="sk-preferred-secret",
        key_id="preferred",
        env_var="OPENAI_API_KEY",
    )

    metadata_text = Path(os.environ["RUMI_DEFAULTSPACK_API_KEYS_PATH"]).read_text(encoding="utf-8")
    assert "sk-provider-secret" not in metadata_text
    assert "sk-agent-secret" not in metadata_text

    resolver = KeyResolver()
    assert resolver.resolve_api_key(provider_id="openai", preferred_key_id="preferred")["api_key_id"] == "preferred"
    assert resolver.resolve_api_key(provider_id="openai", agent_id="agent-1")["api_key_id"] == "agent"
    assert resolver.resolve_api_key(provider_id="openai", profile_id="writer")["api_key_id"] == "profile"
    assert resolver.resolve_api_key(provider_id="openai")["api_key_id"] == "provider"
    assert resolver.resolve_api_key(provider_id="xai", fallback="fallback-value")["source"] == "fallback"

    public = manager.list_keys()[0]
    assert "value" not in public
    assert public["configured"] is True


def test_legacy_provider_key_still_uses_secret_store(monkeypatch, tmp_path):
    from core_runtime.secrets_store import SecretsStore
    from domain.ai_client.api_key_store import load_provider_api_keys_into_env, provider_has_api_key, set_provider_api_key

    _key_env(monkeypatch, tmp_path)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    result = set_provider_api_key("google", "google-secret")
    assert result["success"] is True
    assert result["key"] == "GOOGLE_API_KEY"
    assert SecretsStore(str(tmp_path / "secrets")).has_secret("GOOGLE_API_KEY")
    assert provider_has_api_key("google") is True

    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    loaded = load_provider_api_keys_into_env()
    assert loaded["google"] is True
    assert os.environ["GOOGLE_API_KEY"] == "google-secret"

    metadata = json.loads(Path(os.environ["RUMI_DEFAULTSPACK_API_KEYS_PATH"]).read_text(encoding="utf-8"))
    assert "google-secret" not in json.dumps(metadata)
