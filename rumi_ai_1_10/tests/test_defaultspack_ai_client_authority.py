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


class _TokenAwareAllowAuthority:
    def __init__(self):
        self.calls = []

    def check(self, **kwargs):
        from core_runtime.authority.models import AuthorityDecision

        self.calls.append({
            "permission_id": kwargs["permission_id"],
            "request_id": kwargs.get("request_id"),
            "approval_token": kwargs.get("approval_token"),
        })
        return AuthorityDecision(
            allowed=True,
            permission_id=kwargs["permission_id"],
            principal_id=kwargs["principal_id"],
            reason="allowed",
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


class _CompiledProvider:
    def __init__(self):
        self._api_key = "compiled-secret"
        self._api_key_envs = ["OPENAI_API_KEY"]
        self.request_json_calls = []

    def _request_json(self, path, body):
        self.request_json_calls.append({"path": path, "body": body, "api_key": self._api_key})
        raise AssertionError("compiled provider request used API key before api_key.use authority")


class _CompiledGateway:
    def __init__(self, provider):
        self.provider = provider

    def resolve_provider(self, model):
        return self.provider, model.split("/", 1)[1] if "/" in model else model


def _compiled_prepared_run(provider_id: str = "openai", model: str = "openai/gpt-5.4"):
    from domain.chat.run_request import PreparedChatRun

    return PreparedChatRun(
        conversation_id="c",
        conversation={},
        input_data={},
        request_id="r",
        content=[],
        metadata={},
        user_message={"id": "u"},
        model=model,
        params={},
        request_context={"authority": {"principal_id": "profile:work"}},
        tool_context={},
        standard_messages=[],
        user_text="hi",
        system_prompt="",
        enrich_info={},
        raw_tools=[],
        provider_tools=[],
        tools_called=[],
        connected_tool_names=set(),
        call_handler=None,
        model_routing={},
        provider_capabilities={"provider_id": provider_id, "api_family": "openai_chat"},
    )


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


def test_ai_client_does_not_consume_model_token_before_api_key_approval(monkeypatch):
    client = _client(monkeypatch)
    authority = _DenyApiKeyUseAuthority()
    read_calls = []
    monkeypatch.setattr("core_runtime.authority.get_authority_service", lambda: authority)
    monkeypatch.setattr("domain.ai_client.client.read_provider_api_key", lambda provider_id, api_id: read_calls.append((provider_id, api_id)) or "key")

    from domain.ai_client.client import AuthorityApprovalRequired

    try:
        client.complete(
            "gpt-5.4",
            [{"role": "user", "content": "hi"}],
            params={
                "_authority_context": {
                    "principal_id": "profile:work",
                    "approval_tokens": {
                        "model.invoke": {
                            "request_id": "model_req",
                            "approval_token": "model-token",
                        },
                    },
                },
            },
        )
    except AuthorityApprovalRequired as exc:
        assert exc.decision.permission_id == "api_key.use"
    else:
        raise AssertionError("AuthorityApprovalRequired was not raised")

    assert authority.permissions == ["api_key.use"]
    assert read_calls == []
    assert client._providers["openai"].calls == []


def test_ai_client_uses_permission_specific_authority_tokens(monkeypatch):
    client = _client(monkeypatch)
    authority = _TokenAwareAllowAuthority()
    read_calls = []
    monkeypatch.setattr("core_runtime.authority.get_authority_service", lambda: authority)
    monkeypatch.setattr("domain.ai_client.client.read_provider_api_key", lambda provider_id, api_id: read_calls.append((provider_id, api_id)) or "key")

    response = client.complete(
        "gpt-5.4",
        [{"role": "user", "content": "hi"}],
        params={
            "_authority_context": {
                "principal_id": "profile:work",
                "approval_tokens": {
                    "model.invoke": {
                        "request_id": "model_req",
                        "approval_token": "model-token",
                    },
                    "api_key.use": {
                        "request_id": "api_req",
                        "approval_token": "api-token",
                    },
                },
            },
        },
    )

    assert response["finish_reason"] == "stop"
    assert authority.calls == [
        {"permission_id": "model.invoke", "request_id": "model_req", "approval_token": "model-token"},
        {"permission_id": "api_key.use", "request_id": "api_req", "approval_token": "api-token"},
    ]
    assert read_calls == [("openai", "work")]
    assert client._providers["openai"].calls


def test_authority_followup_metadata_carries_multiple_approval_tokens():
    from domain.chat.run_request import _apply_authority_context

    request_context = {}
    _apply_authority_context(
        request_context,
        {
            "authority_followup": {
                "approval_token": "api-token",
                "request_id": "api_req",
                "permission_id": "api_key.use",
                "approvals": [
                    {
                        "approval_token": "model-token",
                        "request_id": "model_req",
                        "permission_id": "model.invoke",
                    },
                    {
                        "approval_token": "api-token",
                        "request_id": "api_req",
                        "permission_id": "api_key.use",
                    },
                ],
            },
        },
        conversation_id="conv-1",
        request_id="run-1",
        active_profile=None,
    )

    authority = request_context["authority"]
    assert authority["approval_tokens"] == {
        "model.invoke": {
            "approval_token": "model-token",
            "request_id": "model_req",
            "permission_id": "model.invoke",
        },
        "api_key.use": {
            "approval_token": "api-token",
            "request_id": "api_req",
            "permission_id": "api_key.use",
        },
    }


def test_compiled_provider_requires_api_key_use_before_request_json(monkeypatch):
    from domain.ai_client.client import AuthorityApprovalRequired
    from domain.chat.stream_engine import ChatRunEngine

    provider = _CompiledProvider()
    authority = _DenyApiKeyUseAuthority()
    monkeypatch.setattr("core_runtime.authority.get_authority_service", lambda: authority)
    monkeypatch.setattr("domain.ai_client.api_key_store.provider_has_api_key", lambda provider_id: False)

    try:
        ChatRunEngine(store=object(), gateway=_CompiledGateway(provider))._complete_turn_with_compiler(
            _compiled_prepared_run(),
            [{"role": "user", "content": "hi"}],
        )
    except AuthorityApprovalRequired as exc:
        assert exc.decision.permission_id == "api_key.use"
    else:
        raise AssertionError("AuthorityApprovalRequired was not raised")

    assert authority.permissions == ["model.invoke", "api_key.use"]
    assert provider.request_json_calls == []


def test_ai_client_direct_oauth_provider_requires_authority_without_api_key(monkeypatch):
    from domain.ai_client.client import AIClient, AuthorityApprovalRequired
    from domain.ai_client.providers.stub_provider import StubProvider

    AIClient._instance = None
    client = AIClient()
    client._providers = {"stub": StubProvider(), "google": _FakeProvider()}
    monkeypatch.setattr(client, "_routes_for_model", lambda model: [])
    monkeypatch.setattr("domain.ai_client.authority_gate.provider_has_api_key", lambda provider_id: False)
    monkeypatch.setattr(
        "domain.ai_client.authority_gate.provider_has_oauth_connection",
        lambda provider_id: provider_id == "google",
    )
    monkeypatch.setattr("core_runtime.authority.get_authority_service", lambda: _DenyAuthority())

    try:
        client.complete(
            "google/gemini-3",
            [{"role": "user", "content": "hi"}],
            params={"_authority_context": {"principal_id": "profile:work"}},
        )
    except AuthorityApprovalRequired as exc:
        assert exc.decision.permission_id == "model.invoke"
    else:
        raise AssertionError("AuthorityApprovalRequired was not raised")

    assert client._providers["google"].calls == []


def test_compiled_oauth_provider_requires_authority_without_api_key(monkeypatch):
    from domain.ai_client.client import AuthorityApprovalRequired
    from domain.chat.stream_engine import ChatRunEngine

    class OAuthCompiledProvider:
        def __init__(self):
            self.request_json_calls = []

        def _request_json(self, path, body):
            self.request_json_calls.append({"path": path, "body": body})
            raise AssertionError("compiled OAuth provider request ran before authority")

    provider = OAuthCompiledProvider()
    authority = _DenyApiKeyUseAuthority()
    monkeypatch.setattr("core_runtime.authority.get_authority_service", lambda: authority)
    monkeypatch.setattr("domain.ai_client.authority_gate.provider_has_api_key", lambda provider_id: False)
    monkeypatch.setattr(
        "domain.ai_client.authority_gate.provider_has_oauth_connection",
        lambda provider_id: provider_id == "google",
    )

    try:
        ChatRunEngine(store=object(), gateway=_CompiledGateway(provider))._complete_turn_with_compiler(
            _compiled_prepared_run(provider_id="google", model="google/gemini-3"),
            [{"role": "user", "content": "hi"}],
        )
    except AuthorityApprovalRequired as exc:
        assert exc.decision.permission_id == "api_key.use"
    else:
        raise AssertionError("AuthorityApprovalRequired was not raised")

    assert authority.permissions == ["model.invoke", "api_key.use"]
    assert provider.request_json_calls == []


def test_ai_client_auto_register_keeps_oauth_provider_when_cloud_disabled(monkeypatch):
    from domain.ai_client.client import AIClient

    provider = _FakeProvider()
    AIClient._instance = None
    monkeypatch.setattr("domain.ai_client.client.detect_available_providers", lambda: {"oauth-provider": provider})
    monkeypatch.setattr(
        "domain.ai_client.client.get_provider_catalog_map",
        lambda: {"oauth-provider": {"kind": "cloud", "availability": {}}},
    )
    monkeypatch.setattr("domain.ai_client.client.provider_has_api_key", lambda provider_id: False)
    monkeypatch.setattr(
        "domain.ai_client.client.provider_has_oauth_connection",
        lambda provider_id: provider_id == "oauth-provider",
    )

    client = AIClient()

    assert client._providers["oauth-provider"] is provider


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
