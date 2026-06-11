from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


class _FakeProvider:
    def __init__(self):
        self._api_key = ""
        self.calls = []

    def complete(self, model_name, messages, tools, params):
        self.calls.append({"model_name": model_name, "params": params})
        return {"content": [{"type": "text", "text": "ok"}], "finish_reason": "stop"}

    def stream(self, model_name, messages, tools, params):
        self.calls.append({"model_name": model_name, "params": params})
        yield {"type": "stream_end", "finish_reason": "stop"}


class _DenyAuthority:
    def check(self, **kwargs):
        from core_runtime.authority.models import AuthorityDecision

        return AuthorityDecision(
            allowed=False,
            permission_id=kwargs["permission_id"],
            principal_id=kwargs["principal_id"],
            reason="denied",
            request_id="auth_test",
            approval_required=True,
            risk_level="medium",
            resource=kwargs["resource"],
        )


class _AllowAuthority:
    def check(self, **kwargs):
        from core_runtime.authority.models import AuthorityDecision

        return AuthorityDecision(
            allowed=True,
            permission_id=kwargs["permission_id"],
            principal_id=kwargs["principal_id"],
            reason="allowed",
            resource=kwargs["resource"],
        )


class _DenyApiKeyUseAuthority:
    def __init__(self):
        self.permissions = []

    def check(self, **kwargs):
        from core_runtime.authority.models import AuthorityDecision

        self.permissions.append(kwargs["permission_id"])
        allowed = kwargs["permission_id"] == "model.invoke"
        return AuthorityDecision(
            allowed=allowed,
            permission_id=kwargs["permission_id"],
            principal_id=kwargs["principal_id"],
            reason="allowed" if allowed else "api key denied",
            request_id=None if allowed else "auth_api_key_test",
            approval_required=not allowed,
            risk_level="medium",
            resource=kwargs["resource"],
        )


def _client(monkeypatch):
    from domain.ai_client.client import AIClient
    from domain.ai_client.providers.stub_provider import StubProvider

    AIClient._instance = None
    client = AIClient()
    client._providers = {"stub": StubProvider(), "openai": _FakeProvider()}
    monkeypatch.setattr(client, "_routes_for_model", lambda model: ["openai/work"])
    monkeypatch.setattr("domain.ai_client.client.provider_has_api_key", lambda provider_id: True)
    monkeypatch.setattr(
        "domain.ai_client.client.provider_named_api_keys",
        lambda provider_id="": [{"provider_id": "openai", "api_id": "work", "configured": True}],
    )
    monkeypatch.setattr("domain.ai_client.client.provider_api_metadata", lambda provider_id, api_id: {})
    return client


def test_ai_client_does_not_read_api_key_before_authority_allow(monkeypatch):
    client = _client(monkeypatch)
    read_calls = []
    monkeypatch.setattr("core_runtime.authority.get_authority_service", lambda: _DenyAuthority())
    monkeypatch.setattr("domain.ai_client.client.read_provider_api_key", lambda provider_id, api_id: read_calls.append((provider_id, api_id)) or "key")

    from domain.ai_client.client import AuthorityApprovalRequired

    try:
        client.complete("gpt-5.4", [{"role": "user", "content": "hi"}], params={"_authority_context": {"principal_id": "profile:work"}})
    except AuthorityApprovalRequired:
        pass
    else:
        raise AssertionError("AuthorityApprovalRequired was not raised")

    assert read_calls == []
    assert client._providers["openai"].calls == []


def test_ai_client_requires_api_key_use_before_reading_key(monkeypatch):
    client = _client(monkeypatch)
    authority = _DenyApiKeyUseAuthority()
    read_calls = []
    monkeypatch.setattr("core_runtime.authority.get_authority_service", lambda: authority)
    monkeypatch.setattr("domain.ai_client.client.read_provider_api_key", lambda provider_id, api_id: read_calls.append((provider_id, api_id)) or "key")

    from domain.ai_client.client import AuthorityApprovalRequired

    try:
        client.complete("gpt-5.4", [{"role": "user", "content": "hi"}], params={"_authority_context": {"principal_id": "profile:work"}})
    except AuthorityApprovalRequired as exc:
        assert exc.decision.permission_id == "api_key.use"
    else:
        raise AssertionError("AuthorityApprovalRequired was not raised")

    assert authority.permissions == ["model.invoke", "api_key.use"]
    assert read_calls == []
    assert client._providers["openai"].calls == []


def test_ai_client_strips_authority_context_before_provider(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr("core_runtime.authority.get_authority_service", lambda: _AllowAuthority())
    monkeypatch.setattr("domain.ai_client.client.read_provider_api_key", lambda provider_id, api_id: "key")

    response = client.complete(
        "gpt-5.4",
        [{"role": "user", "content": "hi"}],
        params={"temperature": 0, "_authority_context": {"principal_id": "profile:work"}},
    )

    assert response["finish_reason"] == "stop"
    assert client._providers["openai"].calls
    assert client._providers["openai"].calls[0]["params"] == {"temperature": 0}


def test_gateway_keeps_authority_context_out_of_non_authority_clients():
    from domain.ai_client.gateway import LLMGateway

    class FakeClient:
        def __init__(self):
            self.params = None

        def complete(self, model, messages, tools=None, params=None):
            del model, messages, tools
            self.params = dict(params or {})
            return {"content": [{"type": "text", "text": "ok"}], "finish_reason": "stop"}

    client = FakeClient()
    response = LLMGateway(client=client).complete(
        {
            "model": "google/gemma-4-31b-it",
            "messages": [{"role": "user", "content": "hi"}],
            "params": {"temperature": 0.2},
            "authority_context": {"principal_id": "profile:work"},
        }
    )

    assert response["finish_reason"] == "stop"
    assert client.params == {"temperature": 0.2}
