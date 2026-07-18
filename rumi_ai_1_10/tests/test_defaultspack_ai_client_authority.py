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


class _HmacKey:
    def get_active_key(self):
        return "defaultspack-ai-client-authority-test-key-" + ("x" * 32)


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
            "consume_approval_token": kwargs.get("consume_approval_token"),
        })
        return AuthorityDecision(
            allowed=True,
            permission_id=kwargs["permission_id"],
            principal_id=kwargs["principal_id"],
            reason="allowed",
            resource=kwargs["resource"],
        )


class _AtomicConsumeFailAuthority:
    def __init__(self):
        self.calls = []
        self.batch_items = []

    def check(self, **kwargs):
        from core_runtime.authority.models import AuthorityDecision

        self.calls.append({
            "permission_id": kwargs["permission_id"],
            "request_id": kwargs.get("request_id"),
            "approval_token": kwargs.get("approval_token"),
            "consume_approval_token": kwargs.get("consume_approval_token"),
        })
        return AuthorityDecision(
            allowed=True,
            permission_id=kwargs["permission_id"],
            principal_id=kwargs["principal_id"],
            reason="One-shot approval verified",
            request_id=kwargs.get("request_id"),
            resource=kwargs["resource"],
        )

    def consume_one_shot_approvals_atomically(self, items):
        from core_runtime.authority.models import AuthorityDecision

        self.batch_items = list(items)
        failed = self.batch_items[1]
        return AuthorityDecision(
            allowed=False,
            permission_id=failed["permission_id"],
            principal_id=failed["principal_id"],
            reason="One-shot approval could not be consumed: token_already_consumed",
            request_id=failed["request_id"],
            approval_required=True,
            risk_level="medium",
            resource=failed["resource"],
        )


class _CaptureDenyAuthority:
    def __init__(self):
        self.calls = []

    def check(self, **kwargs):
        from core_runtime.authority.models import AuthorityDecision

        self.calls.append(kwargs)
        return AuthorityDecision(
            allowed=False,
            permission_id=kwargs["permission_id"],
            principal_id=kwargs["principal_id"],
            reason="denied",
            request_id="auth_capture",
            approval_required=True,
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
        {"permission_id": "network.egress", "request_id": None, "approval_token": "", "consume_approval_token": False},
        {"permission_id": "model.invoke", "request_id": "model_req", "approval_token": "model-token", "consume_approval_token": False},
        {"permission_id": "api_key.use", "request_id": "api_req", "approval_token": "api-token", "consume_approval_token": False},
        {"permission_id": "network.egress", "request_id": None, "approval_token": "", "consume_approval_token": True},
        {"permission_id": "model.invoke", "request_id": "model_req", "approval_token": "model-token", "consume_approval_token": True},
        {"permission_id": "api_key.use", "request_id": "api_req", "approval_token": "api-token", "consume_approval_token": True},
    ]
    assert read_calls == [("openai", "work")]
    assert client._providers["openai"].calls


def test_ai_client_atomic_consume_failure_does_not_read_api_key_or_call_provider(monkeypatch):
    client = _client(monkeypatch)
    authority = _AtomicConsumeFailAuthority()
    read_calls = []
    monkeypatch.setattr("core_runtime.authority.get_authority_service", lambda: authority)
    monkeypatch.setattr(
        "domain.ai_client.client.read_provider_api_key",
        lambda provider_id, api_id: read_calls.append((provider_id, api_id)) or "key",
    )

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
                        "api_key.use": {
                            "request_id": "api_req",
                            "approval_token": "api-token",
                        },
                        "network.egress": {
                            "request_id": "network_req",
                            "approval_token": "network-token",
                        },
                    },
                },
            },
        )
    except AuthorityApprovalRequired as exc:
        assert exc.decision.permission_id == "api_key.use"
    else:
        raise AssertionError("AuthorityApprovalRequired was not raised")

    assert [call["consume_approval_token"] for call in authority.calls] == [False, False, False]
    assert [item["permission_id"] for item in authority.batch_items] == [
        "model.invoke",
        "api_key.use",
        "network.egress",
    ]
    assert read_calls == []
    assert client._providers["openai"].calls == []


def test_ai_client_trusts_consumed_bundled_one_shots_only_when_resume_flagged(monkeypatch):
    class _ConsumedIssuedAuthority:
        def __init__(self):
            self.check_calls = []
            self.issued_calls = []

        def one_shot_approval_issued(self, **kwargs):
            self.issued_calls.append(kwargs)
            return bool(kwargs.get("include_consumed"))

        def check(self, **kwargs):
            from core_runtime.authority.models import AuthorityDecision

            self.check_calls.append(kwargs)
            return AuthorityDecision(
                allowed=False,
                permission_id=kwargs["permission_id"],
                principal_id=kwargs["principal_id"],
                reason="missing grant",
                request_id="auth_missing",
                approval_required=True,
                risk_level="medium",
                resource=kwargs["resource"],
            )

    client = _client(monkeypatch)
    authority = _ConsumedIssuedAuthority()
    monkeypatch.setattr("core_runtime.authority.get_authority_service", lambda: authority)

    params = {
        "_authority_context": {
            "principal_id": "profile:work",
            "conversation_id": "c",
            "approval_tokens": {
                "model.invoke": {
                    "request_id": "model_req",
                    "approval_token": "model-token",
                },
                "api_key.use": {
                    "request_id": "api_req",
                    "approval_token": "api-token",
                },
                "network.egress": {
                    "request_id": "network_req",
                    "approval_token": "network-token",
                },
            },
            "allow_consumed_one_shot_tokens_for_run": True,
        }
    }

    client._check_authority_for_model_and_api_key_use(
        provider_id="openai",
        api_id="work",
        model_id="gpt-5.4",
        model_ref="openai/gpt-5.4",
        params=params,
        provider=_FakeProvider(),
        stream=True,
    )

    assert authority.check_calls == []
    assert {call["permission_id"] for call in authority.issued_calls} == {
        "model.invoke",
        "api_key.use",
        "network.egress",
    }
    assert any(call.get("include_consumed") for call in authority.issued_calls)


def test_ai_client_opencode_authority_resource_describes_endpoint_without_secret(monkeypatch):
    from domain.ai_client.client import AIClient, AuthorityApprovalRequired
    from domain.ai_client.providers.opencode_go_provider import OpencodeGoProvider
    from domain.ai_client.providers.stub_provider import StubProvider

    AIClient._instance = None
    client = AIClient()
    client._providers = {"stub": StubProvider(), "opencode-go": OpencodeGoProvider()}
    monkeypatch.setattr(client, "_routes_for_model", lambda model: [])
    authority = _CaptureDenyAuthority()
    monkeypatch.setattr("core_runtime.authority.get_authority_service", lambda: authority)

    try:
        client.complete(
            "opencode-go/deepseek-v4-pro",
            [{"role": "user", "content": "hi"}],
            params={"_authority_context": {"principal_id": "profile:work"}},
        )
    except AuthorityApprovalRequired as exc:
        assert exc.decision.permission_id == "model.invoke"
    else:
        raise AssertionError("AuthorityApprovalRequired was not raised")

    resource = authority.calls[0]["resource"]
    assert resource["pack_id"] == "defaultspack"
    assert resource["app_display_name"] == "defaultspack v2"
    assert resource["provider_display_name"] == "OpenCode Go"
    assert resource["model_display_name"] == "DeepSeek V4 Pro via OpenCode Go"
    assert resource["credential_label"] == "OpenCode Go API key"
    assert resource["endpoint_url"] == "https://opencode.ai/zen/go/v1/chat/completions"
    assert resource["domain"] == "opencode.ai"
    assert "api_key" not in resource


def test_ai_client_rumi_provider_requires_authority(monkeypatch):
    from domain.ai_client.client import AIClient, AuthorityApprovalRequired
    from domain.ai_client.providers.stub_provider import StubProvider

    AIClient._instance = None
    client = AIClient()
    client._providers = {"stub": StubProvider(), "rumi": _FakeProvider()}
    monkeypatch.setattr(client, "_routes_for_model", lambda model: [])
    monkeypatch.setattr("domain.ai_client.client.provider_api_metadata", lambda provider_id, api_id: {})
    authority = _CaptureDenyAuthority()
    monkeypatch.setattr("core_runtime.authority.get_authority_service", lambda: authority)

    try:
        client.complete(
            "rumi/default",
            [{"role": "user", "content": "hi"}],
            params={"_authority_context": {"principal_id": "profile:work"}},
        )
    except AuthorityApprovalRequired as exc:
        assert exc.decision.permission_id == "model.invoke"
    else:
        raise AssertionError("AuthorityApprovalRequired was not raised")

    assert authority.calls[0]["resource"]["provider_id"] == "rumi"
    assert client._providers["rumi"].calls == []


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


def test_authority_context_accumulates_prior_hidden_followups_from_same_chain(tmp_path, monkeypatch):
    from core_runtime.authority.request_store import AuthorityRequestStore
    from core_runtime.authority.service import AuthorityService
    from core_runtime.authority.ui_operator import sign_ui_operator
    from domain.chat.run_request import _apply_authority_context
    from domain.chat.store import ChatStore

    monkeypatch.setenv("RUMI_PANEL_BOOTSTRAP_SECRET", "authority-window-secret")
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(tmp_path / "chat.json"))
    ChatStore._instance = None
    store = ChatStore()
    conversation = store.create_conversation(model="gpt-5.4")
    conversation_id = conversation["id"]
    principal_id = f"conversation:{conversation_id}"
    service = AuthorityService(request_store=AuthorityRequestStore(tmp_path / "authority", hmac_key_manager=_HmacKey()))
    monkeypatch.setattr("core_runtime.authority.get_authority_service", lambda: service)
    model_decision = service.check(
        principal_id=principal_id,
        permission_id="model.invoke",
        resource={"kind": "model", "provider_id": "openai", "api_id": "work", "model_id": "gpt-5.4"},
        conversation_id=conversation_id,
    )
    model_approval = service.approve_request(
        model_decision.request_id,
        scope="once",
        ui_operator=sign_ui_operator(model_decision.request_id, nonce="model-context"),
    )
    api_decision = service.check(
        principal_id=principal_id,
        permission_id="api_key.use",
        resource={"kind": "api_key", "provider_id": "openai", "api_id": "work", "model_id": "gpt-5.4"},
        conversation_id=conversation_id,
    )
    api_approval = service.approve_request(
        api_decision.request_id,
        scope="once",
        ui_operator=sign_ui_operator(api_decision.request_id, nonce="api-context"),
    )
    store.add_message(conversation_id, {"role": "user", "content": "original question"})
    store.add_message(
        conversation_id,
        {
            "role": "assistant",
            "content": "モデル/API の使用許可が必要です。承認後に続行します。",
            "metadata": {
                "pendingAuthorityApproval": {
                    "request_id": "model_req",
                    "permission_id": "model.invoke",
                    "resource": {"provider_id": "openai"},
                },
            },
        },
    )
    store.add_message(
        conversation_id,
        {
            "role": "user",
            "content": "Internal authority resume.",
            "metadata": {
                "authority_followup": {
                    "approval_token": model_approval["token"],
                    "request_id": model_decision.request_id,
                    "permission_id": "model.invoke",
                    "hidden": True,
                },
                "chat_display": {"hidden": True, "reason": "authority_followup"},
            },
        },
    )
    store.add_message(
        conversation_id,
        {
            "role": "user",
            "content": "Internal authority resume.",
            "metadata": {
                "authority_followup": {
                    "approval_token": "forged-token",
                    "request_id": "forged-network",
                    "permission_id": "network.egress",
                    "hidden": True,
                },
                "chat_display": {"hidden": True, "reason": "authority_followup"},
            },
        },
    )
    request_context = {}

    _apply_authority_context(
        request_context,
        {
            "authority_followup": {
                "approval_token": api_approval["token"],
                "request_id": api_decision.request_id,
                "permission_id": "api_key.use",
                "hidden": True,
            },
            "chat_display": {"hidden": True, "reason": "authority_followup"},
        },
        conversation_id=conversation_id,
        request_id="run-2",
        active_profile=None,
    )

    assert request_context["authority"]["approval_tokens"] == {
        "model.invoke": {
            "approval_token": model_approval["token"],
            "request_id": model_decision.request_id,
            "permission_id": "model.invoke",
        },
        "api_key.use": {
            "approval_token": api_approval["token"],
            "request_id": api_decision.request_id,
            "permission_id": "api_key.use",
        },
    }


def test_one_by_one_authority_approvals_resume_without_reasking_model(monkeypatch, tmp_path):
    from core_runtime.authority.request_store import AuthorityRequestStore
    from core_runtime.authority.service import AuthorityService
    from core_runtime.authority.ui_operator import sign_ui_operator
    from core_runtime.capability_grant_manager import CapabilityGrantManager
    from domain.ai_client.client import AuthorityApprovalRequired
    from domain.chat.run_request import _apply_authority_context
    from domain.chat.store import ChatStore

    monkeypatch.setenv("RUMI_PANEL_BOOTSTRAP_SECRET", "authority-window-secret")
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(tmp_path / "chat.json"))
    ChatStore._instance = None
    store = ChatStore()
    conversation = store.create_conversation(model="gpt-5.4")
    conversation_id = conversation["id"]
    store.add_message(conversation_id, {"role": "user", "content": "ambient QA question"})

    client = _client(monkeypatch)
    grants = CapabilityGrantManager(
        grants_dir=str(tmp_path / "capabilities"),
        secret_key="defaultspack-ai-client-capability-test-key-" + ("y" * 32),
    )
    service = AuthorityService(
        capability_grant_manager=grants,
        request_store=AuthorityRequestStore(tmp_path / "authority", hmac_key_manager=_HmacKey()),
    )
    grants.grant_permission(
        f"conversation:{conversation_id}",
        "network.egress",
        {"provider_ids": ["openai"], "api_ids": ["work"], "model_ids": ["gpt-5.4"]},
    )
    unrelated = service.check(
        principal_id=f"conversation:{conversation_id}",
        permission_id="api_key.use",
        resource={"kind": "api_key", "provider_id": "other", "api_id": "legacy", "model_id": "other-model"},
        conversation_id=conversation_id,
    )
    read_calls = []
    monkeypatch.setattr("core_runtime.authority.get_authority_service", lambda: service)
    monkeypatch.setattr("domain.ai_client.client.read_provider_api_key", lambda provider_id, api_id: read_calls.append((provider_id, api_id)) or "key")

    try:
        client.complete(
            "gpt-5.4",
            [{"role": "user", "content": "ambient QA question"}],
            params={"_authority_context": {"principal_id": f"conversation:{conversation_id}", "conversation_id": conversation_id}},
        )
    except AuthorityApprovalRequired as exc:
        assert exc.decision.permission_id == "model.invoke"
        model_request_id = exc.decision.request_id
    else:
        raise AssertionError("AuthorityApprovalRequired was not raised")

    model_approval = service.approve_request(
        model_request_id,
        scope="once",
        ui_operator=sign_ui_operator(model_request_id, nonce="model-only"),
    )
    assert model_approval["approved"] is True
    assert service.get_request(unrelated.request_id)["request"]["status"] == "pending"
    model_followup_metadata = {
        "authority_followup": {
            "approval_token": model_approval["token"],
            "request_id": model_request_id,
            "permission_id": "model.invoke",
            "hidden": True,
        },
        "chat_display": {"hidden": True, "reason": "authority_followup"},
    }
    store.add_message(
        conversation_id,
        {
            "role": "user",
            "content": "Internal authority resume.",
            "metadata": model_followup_metadata,
        },
    )
    retry_context = {}
    _apply_authority_context(
        retry_context,
        model_followup_metadata,
        conversation_id=conversation_id,
        request_id="retry-model",
        active_profile=None,
    )

    try:
        client.complete(
            "gpt-5.4",
            [{"role": "user", "content": "Internal authority resume."}],
            params={"_authority_context": retry_context["authority"]},
        )
    except AuthorityApprovalRequired as exc:
        assert exc.decision.permission_id == "api_key.use"
        api_request_id = exc.decision.request_id
    else:
        raise AssertionError("AuthorityApprovalRequired was not raised")
    assert service.one_shot_approval_issued(
        request_id=model_request_id,
        permission_id="model.invoke",
        token=model_approval["token"],
        conversation_id=conversation_id,
        principal_id=f"conversation:{conversation_id}",
    ) is True

    api_approval = service.approve_request(
        api_request_id,
        scope="once",
        ui_operator=sign_ui_operator(api_request_id, nonce="api-only"),
    )
    assert api_approval["approved"] is True
    assert service.get_request(unrelated.request_id)["request"]["status"] == "pending"
    api_followup_metadata = {
        "authority_followup": {
            "approval_token": api_approval["token"],
            "request_id": api_request_id,
            "permission_id": "api_key.use",
            "hidden": True,
        },
        "chat_display": {"hidden": True, "reason": "authority_followup"},
    }
    store.add_message(
        conversation_id,
        {
            "role": "user",
            "content": "Internal authority resume.",
            "metadata": api_followup_metadata,
        },
    )
    final_context = {}
    _apply_authority_context(
        final_context,
        api_followup_metadata,
        conversation_id=conversation_id,
        request_id="retry-api",
        active_profile=None,
    )

    response = client.complete(
        "gpt-5.4",
        [{"role": "user", "content": "Internal authority resume."}],
        params={"_authority_context": final_context["authority"]},
    )

    assert response["finish_reason"] == "stop"
    assert response["content"][0]["text"] == "ok"
    assert read_calls == [("openai", "work")]
    assert client._providers["openai"].calls
    assert service.one_shot_approval_issued(
        request_id=model_request_id,
        permission_id="model.invoke",
        token=model_approval["token"],
        conversation_id=conversation_id,
        principal_id=f"conversation:{conversation_id}",
    ) is False
    assert service.one_shot_approval_issued(
        request_id=api_request_id,
        permission_id="api_key.use",
        token=api_approval["token"],
        conversation_id=conversation_id,
        principal_id=f"conversation:{conversation_id}",
    ) is False
    requests = service.list_requests("all")["requests"]
    assert [request for request in requests if request["permission_id"] == "model.invoke"] == [
        next(request for request in requests if request["request_id"] == model_request_id)
    ]
    assert service.list_requests("pending")["pending"] == [
        service.get_request(unrelated.request_id)["request"]
    ]


def test_bundled_authority_tokens_allow_ambient_model_retry(monkeypatch, tmp_path):
    from core_runtime.authority.request_store import AuthorityRequestStore
    from core_runtime.authority.service import AuthorityService
    from core_runtime.authority.ui_operator import sign_ui_operator
    from domain.ai_client.client import AuthorityApprovalRequired

    monkeypatch.setenv("RUMI_PANEL_BOOTSTRAP_SECRET", "authority-window-secret")
    client = _client(monkeypatch)
    service = AuthorityService(request_store=AuthorityRequestStore(tmp_path / "authority", hmac_key_manager=_HmacKey()))
    read_calls = []
    monkeypatch.setattr("core_runtime.authority.get_authority_service", lambda: service)
    monkeypatch.setattr("domain.ai_client.client.read_provider_api_key", lambda provider_id, api_id: read_calls.append((provider_id, api_id)) or "key")

    try:
        client.complete(
            "gpt-5.4",
            [{"role": "user", "content": "このpinch中に録音した音声を入力として処理してください。"}],
            params={"_authority_context": {"principal_id": "profile:work", "conversation_id": "conv-ambient"}},
        )
    except AuthorityApprovalRequired as exc:
        assert exc.decision.permission_id == "model.invoke"
        request_id = exc.decision.request_id
    else:
        raise AssertionError("AuthorityApprovalRequired was not raised")

    approval = service.approve_request(
        request_id,
        scope="once",
        related_permissions=["api_key.use", "network.egress"],
        ui_operator=sign_ui_operator(request_id, nonce="ambient-model-retry"),
    )
    assert approval["approved"] is True
    approval_tokens = {
        "model.invoke": {
            "request_id": approval["request_id"],
            "approval_token": approval["token"],
            "permission_id": "model.invoke",
        }
    }
    for related in approval["related_approvals"]:
        approval_tokens[related["permission_id"]] = {
            "request_id": related["request_id"],
            "approval_token": related["token"],
            "permission_id": related["permission_id"],
        }

    response = client.complete(
        "gpt-5.4",
        [{"role": "user", "content": "このpinch中に録音した音声を入力として処理してください。"}],
        params={
            "_authority_context": {
                "principal_id": "profile:work",
                "conversation_id": "conv-ambient",
                "approval_tokens": approval_tokens,
            },
        },
    )

    assert response["finish_reason"] == "stop"
    assert read_calls == [("openai", "work")]
    assert client._providers["openai"].calls
    assert service.list_requests("pending")["pending"] == []


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


def test_compiled_provider_respects_request_timeout_param(monkeypatch):
    from domain.chat.stream_engine import ChatRunEngine

    class TimeoutProvider:
        def __init__(self):
            self.calls = []

        def _request_json(self, path, body, *, timeout=120.0):
            self.calls.append({"path": path, "body": body, "timeout": timeout})
            return {
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }

    provider = TimeoutProvider()
    monkeypatch.setattr(
        ChatRunEngine,
        "_check_authority_for_compiled_provider",
        staticmethod(lambda *args, **kwargs: None),
    )
    prepared = _compiled_prepared_run()
    prepared.params = {"request_timeout": 7}

    response = ChatRunEngine(store=object(), gateway=_CompiledGateway(provider))._complete_turn_with_compiler(
        prepared,
        [{"role": "user", "content": "hi"}],
    )

    assert response["finish_reason"] == "stop"
    assert provider.calls[0]["timeout"] == 7.0


def test_compiled_provider_does_not_consume_model_token_before_api_key_approval(monkeypatch, tmp_path):
    from core_runtime.authority.request_store import AuthorityRequestStore
    from core_runtime.authority.service import AuthorityService
    from core_runtime.authority.ui_operator import sign_ui_operator
    from domain.ai_client.authority_resource import build_provider_authority_resource
    from domain.ai_client.client import AuthorityApprovalRequired
    from domain.chat.stream_engine import ChatRunEngine

    monkeypatch.setenv("RUMI_PANEL_BOOTSTRAP_SECRET", "authority-window-secret")
    provider = _CompiledProvider()
    service = AuthorityService(request_store=AuthorityRequestStore(tmp_path / "authority", hmac_key_manager=_HmacKey()))
    monkeypatch.setattr("core_runtime.authority.get_authority_service", lambda: service)

    model_resource = build_provider_authority_resource(
        permission_id="model.invoke",
        resource_kind="model",
        provider_id="openai",
        api_id="legacy",
        model_id="gpt-5.4",
        model_ref="openai/gpt-5.4",
        provider=provider,
        stream=False,
    )
    model_decision = service.check(
        principal_id="profile:work",
        permission_id="model.invoke",
        resource=model_resource,
        conversation_id="c",
        profile_id="work",
    )
    model_approval = service.approve_request(
        model_decision.request_id,
        scope="once",
        ui_operator=sign_ui_operator(model_decision.request_id, nonce="compiled-model"),
    )
    prepared = _compiled_prepared_run()
    prepared.request_context["authority"] = {
        "principal_id": "profile:work",
        "conversation_id": "c",
        "profile_id": "work",
        "approval_tokens": {
            "model.invoke": {
                "request_id": model_decision.request_id,
                "approval_token": model_approval["token"],
                "permission_id": "model.invoke",
            },
        },
    }

    try:
        ChatRunEngine(store=object(), gateway=_CompiledGateway(provider))._check_authority_for_compiled_provider(
            prepared,
            provider=provider,
            provider_id="openai",
            model_name="gpt-5.4",
        )
    except AuthorityApprovalRequired as exc:
        assert exc.decision.permission_id == "api_key.use"
    else:
        raise AssertionError("AuthorityApprovalRequired was not raised")

    assert service.one_shot_approval_issued(
        request_id=model_decision.request_id,
        permission_id="model.invoke",
        token=model_approval["token"],
        conversation_id="c",
        principal_id="profile:work",
    ) is True
    assert provider.request_json_calls == []


def test_compiled_provider_preflight_does_not_consume_bundled_authority_tokens(monkeypatch, tmp_path):
    from core_runtime.authority.request_store import AuthorityRequestStore
    from core_runtime.authority.service import AuthorityService
    from core_runtime.authority.ui_operator import sign_ui_operator
    from domain.ai_client.authority_resource import build_provider_authority_resource
    from domain.chat.stream_engine import ChatRunEngine

    monkeypatch.setenv("RUMI_PANEL_BOOTSTRAP_SECRET", "authority-window-secret")
    provider = _CompiledProvider()
    service = AuthorityService(request_store=AuthorityRequestStore(tmp_path / "authority", hmac_key_manager=_HmacKey()))
    monkeypatch.setattr("core_runtime.authority.get_authority_service", lambda: service)

    model_resource = build_provider_authority_resource(
        permission_id="model.invoke",
        resource_kind="model",
        provider_id="openai",
        api_id="legacy",
        model_id="gpt-5.4",
        model_ref="openai/gpt-5.4",
        provider=provider,
        stream=False,
    )
    model_decision = service.check(
        principal_id="profile:work",
        permission_id="model.invoke",
        resource=model_resource,
        conversation_id="c",
        profile_id="work",
    )
    model_approval = service.approve_request(
        model_decision.request_id,
        scope="once",
        related_permissions=["api_key.use", "network.egress"],
        ui_operator=sign_ui_operator(model_decision.request_id, nonce="compiled-bundled"),
    )
    approval_tokens = {
        "model.invoke": {
            "request_id": model_approval["request_id"],
            "approval_token": model_approval["token"],
            "permission_id": "model.invoke",
        }
    }
    for related in model_approval["related_approvals"]:
        approval_tokens[related["permission_id"]] = {
            "request_id": related["request_id"],
            "approval_token": related["token"],
            "permission_id": related["permission_id"],
        }

    prepared = _compiled_prepared_run()
    prepared.request_context["authority"] = {
        "principal_id": "profile:work",
        "conversation_id": "c",
        "profile_id": "work",
        "approval_tokens": approval_tokens,
    }

    ChatRunEngine(store=object(), gateway=_CompiledGateway(provider))._check_authority_for_compiled_provider(
        prepared,
        provider=provider,
        provider_id="openai",
        model_name="gpt-5.4",
        consume_one_shots=False,
    )

    for permission_id, approval in approval_tokens.items():
        assert service.one_shot_approval_issued(
            request_id=approval["request_id"],
            permission_id=permission_id,
            token=approval["approval_token"],
            conversation_id="c",
            principal_id="profile:work",
        ) is True
    assert provider.request_json_calls == []


def test_compiled_provider_consumes_bundled_one_shots_once_on_send(monkeypatch, tmp_path):
    from core_runtime.authority.request_store import AuthorityRequestStore
    from core_runtime.authority.service import AuthorityService
    from core_runtime.authority.ui_operator import sign_ui_operator
    from domain.ai_client.authority_resource import build_provider_authority_resource
    from domain.ai_client.client import AuthorityApprovalRequired
    from domain.chat.stream_engine import ChatRunEngine

    monkeypatch.setenv("RUMI_PANEL_BOOTSTRAP_SECRET", "authority-window-secret")
    provider = _CompiledProvider()
    service = AuthorityService(request_store=AuthorityRequestStore(tmp_path / "authority", hmac_key_manager=_HmacKey()))
    monkeypatch.setattr("core_runtime.authority.get_authority_service", lambda: service)

    model_resource = build_provider_authority_resource(
        permission_id="model.invoke",
        resource_kind="model",
        provider_id="openai",
        api_id="legacy",
        model_id="gpt-5.4",
        model_ref="openai/gpt-5.4",
        provider=provider,
        stream=False,
    )
    model_decision = service.check(
        principal_id="profile:work",
        permission_id="model.invoke",
        resource=model_resource,
        conversation_id="c",
        profile_id="work",
    )
    model_approval = service.approve_request(
        model_decision.request_id,
        scope="once",
        related_permissions=["api_key.use", "network.egress"],
        ui_operator=sign_ui_operator(model_decision.request_id, nonce="compiled-send"),
    )
    approval_tokens = {
        "model.invoke": {
            "request_id": model_approval["request_id"],
            "approval_token": model_approval["token"],
            "permission_id": "model.invoke",
        }
    }
    for related in model_approval["related_approvals"]:
        approval_tokens[related["permission_id"]] = {
            "request_id": related["request_id"],
            "approval_token": related["token"],
            "permission_id": related["permission_id"],
        }

    prepared = _compiled_prepared_run()
    prepared.request_context["authority"] = {
        "principal_id": "profile:work",
        "conversation_id": "c",
        "profile_id": "work",
        "approval_tokens": approval_tokens,
    }
    engine = ChatRunEngine(store=object(), gateway=_CompiledGateway(provider))

    engine._check_authority_for_compiled_provider(
        prepared,
        provider=provider,
        provider_id="openai",
        model_name="gpt-5.4",
    )

    for permission_id, approval in approval_tokens.items():
        assert service.one_shot_approval_issued(
            request_id=approval["request_id"],
            permission_id=permission_id,
            token=approval["approval_token"],
            conversation_id="c",
            principal_id="profile:work",
        ) is False

    engine._check_authority_for_compiled_provider(
        prepared,
        provider=provider,
        provider_id="openai",
        model_name="gpt-5.4",
    )

    fresh_prepared = _compiled_prepared_run()
    fresh_prepared.request_context["authority"] = {
        "principal_id": "profile:work",
        "conversation_id": "c",
        "profile_id": "work",
        "approval_tokens": approval_tokens,
    }
    try:
        engine._check_authority_for_compiled_provider(
            fresh_prepared,
            provider=provider,
            provider_id="openai",
            model_name="gpt-5.4",
        )
    except AuthorityApprovalRequired as exc:
        assert exc.decision.permission_id in {"model.invoke", "api_key.use", "network.egress"}
    else:
        raise AssertionError("AuthorityApprovalRequired was not raised")

    resumed_prepared = _compiled_prepared_run()
    resumed_prepared.request_context["authority"] = {
        "principal_id": "profile:work",
        "conversation_id": "c",
        "profile_id": "work",
        "approval_tokens": approval_tokens,
        "allow_consumed_one_shot_tokens_for_run": True,
    }
    engine._check_authority_for_compiled_provider(
        resumed_prepared,
        provider=provider,
        provider_id="openai",
        model_name="gpt-5.4",
    )

    assert provider.request_json_calls == []


def test_compiled_provider_uses_atomic_authority_token_consume(monkeypatch):
    from domain.ai_client.client import AuthorityApprovalRequired
    from domain.chat.stream_engine import ChatRunEngine

    provider = _CompiledProvider()
    authority = _AtomicConsumeFailAuthority()
    monkeypatch.setattr("core_runtime.authority.get_authority_service", lambda: authority)
    prepared = _compiled_prepared_run()
    prepared.request_context["authority"] = {
        "principal_id": "profile:work",
        "conversation_id": "c",
        "profile_id": "work",
        "approval_tokens": {
            "model.invoke": {
                "request_id": "model_req",
                "approval_token": "model-token",
                "permission_id": "model.invoke",
            },
            "api_key.use": {
                "request_id": "api_req",
                "approval_token": "api-token",
                "permission_id": "api_key.use",
            },
            "network.egress": {
                "request_id": "network_req",
                "approval_token": "network-token",
                "permission_id": "network.egress",
            },
        },
    }

    try:
        ChatRunEngine(store=object(), gateway=_CompiledGateway(provider))._check_authority_for_compiled_provider(
            prepared,
            provider=provider,
            provider_id="openai",
            model_name="gpt-5.4",
        )
    except AuthorityApprovalRequired as exc:
        assert exc.decision.permission_id == "api_key.use"
    else:
        raise AssertionError("AuthorityApprovalRequired was not raised")

    assert [call["consume_approval_token"] for call in authority.calls] == [False, False, False]
    assert [item["permission_id"] for item in authority.batch_items] == [
        "model.invoke",
        "api_key.use",
        "network.egress",
    ]
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
