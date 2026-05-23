from __future__ import annotations

import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.chat.store import ChatStore  # noqa: E402
from domain.chat.run_request import prepare_chat_run  # noqa: E402
from domain.external.token_store import read_external_token, set_external_token  # noqa: E402
from domain.function_runtime.dispatcher import run_defaultspack_function  # noqa: E402
from domain.input import RumiInputEnvelope, dispatch_input, submit_input  # noqa: E402
from domain.webhook.endpoint_store import WebhookEndpointStore  # noqa: E402
from domain.webhook.inbound import handle_inbound_webhook  # noqa: E402
from domain.ai_client.model_call import call_model  # noqa: E402
from domain.ai_client.model_pack_store import ModelPackStore  # noqa: E402
from domain.ai_client.model_router import ModelRoutingDecision, ModelRoutingRequest, route_model_request  # noqa: E402
from domain.ai_client.client import AIClient  # noqa: E402


def _configure_paths(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(tmp_path / "chat" / "conversations.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_INTEGRATIONS_STORE_PATH", str(tmp_path / "integrations" / "conversations.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_INTEGRATIONS_LOCKS_DIR", str(tmp_path / "integrations" / "event_locks"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_STEER_STORE_PATH", str(tmp_path / "chat" / "steer_queue.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_WEBHOOK_ENDPOINTS_PATH", str(tmp_path / "webhooks" / "endpoints.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_SECRETS_DIR", str(tmp_path / "secrets"))
    ChatStore._instance = None


def _conversation(tmp_path: Path) -> dict:
    ChatStore._instance = None
    return ChatStore().create_conversation(model="stub/default")


def _fake_route_decision(model: str) -> ModelRoutingDecision:
    return ModelRoutingDecision(
        selected_model=model,
        original_model=model,
        selected_group="default",
        reason_codes=["test"],
        warnings=[],
        bridge_required=False,
        bridge_plan={},
        utility_models={},
        explanation="test",
    )


def _tiny_image_attachment() -> dict:
    return {
        "id": "img-1",
        "name": "tiny.png",
        "type": "image/png",
        "dataUrl": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/axR4xUAAAAASUVORK5CYII=",
        "size": 68,
    }


def test_input_envelope_accepts_target_delivery_attachments():
    envelope = RumiInputEnvelope.from_dict(
        {
            "input": "hello",
            "target": {"conversation_id": "conv-1"},
            "delivery": {"action_id": "run.instruction"},
            "attachments": [{"id": "a1"}],
        }
    )

    assert envelope.target == {"conversation_id": "conv-1"}
    assert envelope.delivery == {"action_id": "run.instruction"}
    assert envelope.attachments == [{"id": "a1"}]


def test_submit_input_defaults_to_chat_message(monkeypatch, tmp_path):
    _configure_paths(monkeypatch, tmp_path)
    conversation = _conversation(tmp_path)

    monkeypatch.setattr(
        "blocks.chat.send.run",
        lambda request, context: {
            "status": "ok",
            "data": {"id": "assistant-1", "content": [{"type": "text", "text": "hi"}]},
        },
    )

    result = submit_input(
        {
            "role": "user",
            "input": "hello",
            "chat": {"conversation_id": conversation["id"]},
            "source": {"kind": "internal", "provider": "internal"},
            "target": {"conversation_id": conversation["id"], "direct": True},
        },
        {},
    )

    assert result["status"] == "ok"
    assert result["action_id"] == "chat.message"
    assert result["conversation_id"] == conversation["id"]


def test_generic_webhook_delivery_chat_message(monkeypatch, tmp_path):
    _configure_paths(monkeypatch, tmp_path)
    conversation = _conversation(tmp_path)
    WebhookEndpointStore().upsert(
        {
            "id": "generic-chat",
            "kind": "generic",
            "input_profile_id": "generic.webhook.default",
            "enabled": True,
            "target": {"conversation_id": conversation["id"], "direct": True},
            "default_delivery": {"action_id": "chat.message"},
            "allowed_delivery_actions": ["chat.message", "run.instruction"],
        }
    )
    set_external_token("generic", "secret", token_id="generic-chat", kind="webhook_shared_secret")
    monkeypatch.setattr(
        "blocks.chat.send.run",
        lambda request, context: {
            "status": "ok",
            "data": {"id": "assistant-2", "content": [{"type": "text", "text": "sent"}]},
        },
    )

    result = handle_inbound_webhook(
        "generic-chat",
        {"text": "hello", "_headers": {"x-rumi-webhook-token": "secret"}, "action_id": "chat.message"},
        {},
    )

    assert result["status"] == "ok"
    assert result["result"]["action_id"] == "chat.message"
    assert result["result"]["conversation_id"] == conversation["id"]


def test_generic_webhook_delivery_run_instruction(monkeypatch, tmp_path):
    _configure_paths(monkeypatch, tmp_path)
    conversation = _conversation(tmp_path)
    WebhookEndpointStore().upsert(
        {
            "id": "generic-steer",
            "kind": "generic",
            "input_profile_id": "generic.webhook.default",
            "enabled": True,
            "target": {"conversation_id": conversation["id"]},
            "default_delivery": {"action_id": "run.instruction"},
        }
    )
    set_external_token("generic", "secret", token_id="generic-steer", kind="webhook_shared_secret")

    result = handle_inbound_webhook(
        "generic-steer",
        {"text": "please continue", "_headers": {"x-rumi-webhook-token": "secret"}},
        {},
    )

    assert result["status"] == "ok"
    assert result["result"]["action_id"] == "run.instruction"
    assert result["result"]["instruction"]["conversation_id"] == conversation["id"]


def test_generic_webhook_rejects_disallowed_delivery_action(monkeypatch, tmp_path):
    _configure_paths(monkeypatch, tmp_path)
    _conversation(tmp_path)
    WebhookEndpointStore().upsert(
        {
            "id": "generic-locked",
            "kind": "generic",
            "input_profile_id": "generic.webhook.default",
            "enabled": True,
            "allowed_delivery_actions": ["chat.message"],
        }
    )
    set_external_token("generic", "secret", token_id="generic-locked", kind="webhook_shared_secret")

    result = handle_inbound_webhook(
        "generic-locked",
        {"text": "nope", "_headers": {"x-rumi-webhook-token": "secret"}, "action_id": "run.instruction"},
        {},
    )

    assert result["status"] == "error"
    assert result["code"] == "WEBHOOK_DELIVERY_ACTION_NOT_ALLOWED"


def test_input_endpoint_create_returns_localhost_url_with_secret(monkeypatch, tmp_path):
    _configure_paths(monkeypatch, tmp_path)
    monkeypatch.setenv("DEFAULTS_HTTP_PORT", "9911")

    result = run_defaultspack_function(
        "input_endpoint_create",
        {"shared_secret": "super-secret", "ttl_seconds": 120, "action_id": "run.instruction"},
        {},
    )

    data = result["data"]
    assert data["localhost_url"].startswith("http://localhost:9911/api/webhooks/inbound/")
    assert data["shared_secret"] == "super-secret"
    assert read_external_token("generic", token_id=data["endpoint_id"], kind="webhook_shared_secret") == "super-secret"


def test_input_endpoint_ttl_expired_rejected(monkeypatch, tmp_path):
    _configure_paths(monkeypatch, tmp_path)
    WebhookEndpointStore().upsert(
        {
            "id": "expired-webhook",
            "kind": "generic",
            "input_profile_id": "generic.webhook.default",
            "enabled": True,
            "expires_at": 1,
        }
    )
    set_external_token("generic", "secret", token_id="expired-webhook", kind="webhook_shared_secret")

    result = handle_inbound_webhook(
        "expired-webhook",
        {"text": "expired", "_headers": {"x-rumi-webhook-token": "secret"}},
        {},
    )

    assert result["status"] == "error"
    assert result["code"] == "WEBHOOK_EXPIRED"
    assert result["_http_status"] == 410


def test_agent_delegate_action_starts_agent_with_tools_params_capabilities(monkeypatch, tmp_path):
    _configure_paths(monkeypatch, tmp_path)
    seen: dict[str, object] = {}

    def fake_execute(input_data, context):
        seen["input_data"] = input_data
        seen["context"] = context
        return {"status": "ok", "data": {"execution_id": "agent-1", "status": "queued"}}

    monkeypatch.setattr("blocks.agent.execute.run", fake_execute)

    result = dispatch_input(
        {
            "input": "",
            "target": {"conversation_id": "conv-1"},
            "delivery": {"action_id": "agent.delegate"},
            "params": {
                "delegate": {
                    "task": "check the docs",
                    "tools": ["web_search"],
                    "required_capabilities": ["runtime.workspace"],
                    "params": {"mode": "review"},
                }
            },
        },
        {},
    )

    assert result["status"] == "ok"
    assert seen["input_data"]["tools"] == ["web_search"]
    assert seen["input_data"]["required_capabilities"] == ["runtime.workspace"]
    assert seen["input_data"]["params"] == {"mode": "review"}


def test_model_pack_selects_vision_member_for_images():
    profiles = [
        {"profile_id": "demo/text", "qualified_model_id": "demo/text", "provider_id": "demo", "model_id": "text", "type": "chat", "configured": True, "supports_vision": False, "supports_tool_calling": False, "supports_thinking": False},
        {"profile_id": "demo/vision", "qualified_model_id": "demo/vision", "provider_id": "demo", "model_id": "vision", "type": "chat", "configured": True, "supports_vision": True, "supports_tool_calling": True, "supports_thinking": True},
    ]
    settings = {"model_packs": [{"id": "triage", "members": [{"model": "demo/text"}, {"model": "demo/vision"}]}], "preferred_model_group": "default", "model_groups": {"default": {"allowed_models": []}}}

    decision = route_model_request(
        ModelRoutingRequest(has_images=True, preferred_model="modelpack/triage", settings=settings),
        profiles=profiles,
    )

    assert decision.selected_model == "demo/vision"
    assert "model_pack_selected" in decision.reason_codes


def test_model_pack_selects_tool_member_for_tool_calling():
    profiles = [
        {"profile_id": "demo/text", "qualified_model_id": "demo/text", "provider_id": "demo", "model_id": "text", "type": "chat", "configured": True, "supports_vision": False, "supports_tool_calling": False, "supports_thinking": False},
        {"profile_id": "demo/tool", "qualified_model_id": "demo/tool", "provider_id": "demo", "model_id": "tool", "type": "chat", "configured": True, "supports_vision": False, "supports_tool_calling": True, "supports_thinking": True},
    ]
    settings = {"model_packs": [{"id": "triage", "members": [{"model": "demo/text"}, {"model": "demo/tool"}]}], "preferred_model_group": "default", "model_groups": {"default": {"allowed_models": []}}}

    decision = route_model_request(
        ModelRoutingRequest(requires_tool_calling=True, preferred_model="modelpack/triage", settings=settings),
        profiles=profiles,
    )

    assert decision.selected_model == "demo/tool"


def test_model_pack_fallback_chain(monkeypatch, tmp_path):
    settings_path = tmp_path / "frontend_settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "models": {
                    "model_packs": [
                        {
                            "id": "fallback-pack",
                            "members": [
                                {"model": "demo/primary", "fallback_on": ["any"]},
                                {"model": "demo/backup"},
                            ],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(AIClient, "_settings_path", lambda self: settings_path)

    class PrimaryProvider:
        def complete(self, model_name, messages, tools, params):
            raise RuntimeError("rate limit")

    class BackupProvider:
        def complete(self, model_name, messages, tools, params):
            return {"content": [{"type": "text", "text": "backup ok"}], "metadata": {}}

    def fake_resolve(self, model):
        if model == "demo/primary":
            return PrimaryProvider(), "primary"
        if model == "demo/backup":
            return BackupProvider(), "backup"
        raise AssertionError(model)

    monkeypatch.setattr(AIClient, "resolve_provider", fake_resolve)

    response = AIClient().complete("modelpack/fallback-pack", [{"role": "user", "content": "hi"}], [], {})

    assert response["content"][0]["text"] == "backup ok"
    assert response["metadata"]["model_pack"]["pack_id"] == "fallback-pack"


def test_model_call_uses_required_capabilities(monkeypatch):
    seen: dict[str, object] = {}

    def fake_route(request, profiles=None):
        del profiles
        seen["requires_tool_calling"] = request.requires_tool_calling
        return _fake_route_decision("demo/tool")

    monkeypatch.setattr("domain.ai_client.model_call.route_model_request", fake_route)
    monkeypatch.setattr("domain.ai_client.model_call.LLMGateway.complete", lambda self, request: {"content": [{"type": "text", "text": "ok"}]})

    result = call_model({"question": "hello", "required_capabilities": ["model.tool_calling"]})

    assert result["status"] == "ok"
    assert result["model"] == "demo/tool"
    assert seen["requires_tool_calling"] is True


def test_model_call_does_not_forward_secrets(monkeypatch):
    seen: dict[str, object] = {}

    def fake_complete(self, request):
        seen["messages"] = request["messages"]
        return {"content": [{"type": "text", "text": "ok"}]}

    monkeypatch.setattr("domain.ai_client.model_call.LLMGateway.complete", fake_complete)

    result = call_model(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "hello",
                    "metadata": {"api_key": "secret", "safe": "ok"},
                }
            ]
        }
    )

    assert result["status"] == "ok"
    assert "api_key" not in json.dumps(seen["messages"], ensure_ascii=False)


def test_model_switch_updates_conversation_default(monkeypatch, tmp_path):
    _configure_paths(monkeypatch, tmp_path)
    conversation = _conversation(tmp_path)

    result = dispatch_input(
        {
            "delivery": {"action_id": "model.switch"},
            "target": {"conversation_id": conversation["id"]},
            "params": {"model": "demo/next"},
        },
        {},
    )

    assert result["status"] == "ok"
    assert ChatStore().get_conversation(conversation["id"])["model"] == "demo/next"


def test_model_route_is_turn_scoped(monkeypatch, tmp_path):
    _configure_paths(monkeypatch, tmp_path)
    conversation = _conversation(tmp_path)
    dispatch_input(
        {
            "delivery": {"action_id": "model.route"},
            "target": {"conversation_id": conversation["id"]},
            "params": {"model": "demo/route-once"},
        },
        {},
    )

    monkeypatch.setattr("domain.chat.run_request.route_model_request", lambda request: _fake_route_decision(request.preferred_model))
    monkeypatch.setattr("domain.chat.run_request.get_model_capabilities", lambda model: {"supports_thinking": True, "supports_tool_calling": False})

    prepared = prepare_chat_run(
        {"conversation_id": conversation["id"], "message": {"role": "user", "content": "hello"}},
        {},
    )

    assert prepared.model == "demo/route-once"
    assert "turn_model_route_override" not in (ChatStore().get_conversation(conversation["id"]).get("metadata") or {})


def test_composite_models_compat_with_model_pack():
    store = ModelPackStore({"composite_models": [{"id": "legacy-pack", "members": [{"model": "demo/text"}]}]})

    pack = store.get("modelpack/legacy-pack")

    assert pack is not None
    assert pack.source == "composite_compat"
