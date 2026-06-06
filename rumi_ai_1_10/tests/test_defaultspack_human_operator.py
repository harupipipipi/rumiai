from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


from domain.chat.run_request import _available_tools  # noqa: E402
from domain.chat.store import ChatStore  # noqa: E402
from domain.human_operator.constants import (  # noqa: E402
    HUMAN_OPERATOR_MODEL,
    HUMAN_OPERATOR_TOOL_NAME,
)
from domain.human_operator.session_store import load_session  # noqa: E402


@pytest.fixture
def isolated_chat_store(monkeypatch, tmp_path):
    chat_store_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(chat_store_path))
    yield chat_store_path


def test_human_operator_provider_catalog_and_models():
    from domain.ai_client.client import AIClient
    from domain.ai_client.providers import detect_available_providers, get_all_known_models, get_provider_catalog_map

    catalog = get_provider_catalog_map()
    models = {item["id"]: item for item in get_all_known_models("human-operator")}
    available = detect_available_providers()
    AIClient._instance = None
    client = AIClient()
    provider, model_name = client.resolve_provider(HUMAN_OPERATOR_MODEL)

    assert catalog["human-operator"]["metadata"]["adapter"] == "python_entrypoint"
    assert catalog["human-operator"]["default_model"] == "command-canvas"
    assert catalog["human-operator"]["availability"]["supports_invoke"] is True
    assert catalog["human-operator"]["availability"]["configuration_source"] == "builtin_local_provider"
    assert HUMAN_OPERATOR_MODEL in models
    assert models[HUMAN_OPERATOR_MODEL]["metadata"]["command_only"] is True
    assert getattr(available["human-operator"], "provider_id", "") == "human-operator"
    assert available["human-operator"].__class__.__name__ == "HumanOperatorProvider"
    assert provider.__class__.__name__ == "HumanOperatorProvider"
    assert model_name == "command-canvas"


def test_human_operator_provider_start_uses_canvas_tool():
    from domain.ai_client.providers.human_operator_provider import HumanOperatorProvider

    provider = HumanOperatorProvider()
    response = provider.complete(
        HUMAN_OPERATOR_MODEL,
        [{"role": "user", "content": "/start review the prompt"}],
        [{"type": "function", "function": {"name": HUMAN_OPERATOR_TOOL_NAME, "parameters": {"type": "object"}}}],
        {"temperature": 0},
    )

    tool_use = response["content"][0]
    assert response["finish_reason"] == "tool_calls"
    assert tool_use["type"] == "tool_use"
    assert tool_use["name"] == HUMAN_OPERATOR_TOOL_NAME
    assert tool_use["input"]["note"] == "review the prompt"
    assert tool_use["input"]["model"] == HUMAN_OPERATOR_MODEL


def test_human_operator_plain_text_is_rejected():
    from domain.ai_client.providers.human_operator_provider import HumanOperatorProvider

    provider = HumanOperatorProvider()
    response = provider.complete(
        HUMAN_OPERATOR_MODEL,
        [{"role": "user", "content": "hello"}],
        [],
        {},
    )

    assert response["finish_reason"] == "stop"
    assert "only accepts commands" in response["content"][0]["text"]


def test_human_operator_model_auto_attaches_canvas_tool():
    raw_tools, provider_tools, tool_context = _available_tools(
        {"model": HUMAN_OPERATOR_MODEL},
        {"message": {"content": "/start"}},
        user_text="/start",
    )

    assert HUMAN_OPERATOR_TOOL_NAME in {tool["tool_id"] for tool in raw_tools}
    assert HUMAN_OPERATOR_TOOL_NAME in {
        tool["function"]["name"]
        for tool in provider_tools
        if isinstance(tool, dict) and isinstance(tool.get("function"), dict)
    }
    assert tool_context["model"] == HUMAN_OPERATOR_MODEL


def test_human_operator_tool_creates_session_and_routes_append_messages(isolated_chat_store):
    from blocks.human_operator.append_message import run as append_message_run
    from blocks.human_operator.page import run as page_run
    from domain.tool.human_operator_tools import human_operator_canvas_open

    store = ChatStore()
    conversation = store.create_conversation(model=HUMAN_OPERATOR_MODEL)
    context = {
        "conversation_id": conversation["id"],
        "conversation_workspace_dir": str(store.conversation_workspace_dir(conversation["id"])),
        "model": HUMAN_OPERATOR_MODEL,
        "chat_params": {"temperature": 0},
    }
    result = human_operator_canvas_open(
        {
            "session_id": "humanop_test",
            "command": "/start",
            "messages": [
                {"role": "system", "content": "You are a careful reviewer."},
                {"role": "user", "content": "/start"},
            ],
            "params": {"temperature": 0},
            "tool_names": [HUMAN_OPERATOR_TOOL_NAME],
        },
        context,
    )

    local_url = result["widget"]["data"]["local_url"]
    assert "/api/human-operator/conversations/{}/sessions/humanop_test".format(conversation["id"]) in local_url

    session = load_session(conversation["id"], "humanop_test")
    assert session is not None
    assert session["launch_snapshot"]["system_prompt"] == "You are a careful reviewer."
    assert isinstance(session["csrf_token"], str)
    assert len(session["csrf_token"]) >= 32

    page = page_run(
        {
            "conversation_id": conversation["id"],
            "session_id": "humanop_test",
            "view": "readable",
            "prompt_view": "original",
        },
        {},
    )
    assert page["_static"] is True
    assert "Human Operator Canvas" in page["body"]
    assert 'name="csrf_token"' in page["body"]

    rejected = append_message_run(
        {
            "conversation_id": conversation["id"],
            "session_id": "humanop_test",
            "role": "assistant",
            "text": "I should not be appended.",
            "content_format": "text",
            "csrf_token": "wrong",
        },
        {},
    )
    assert rejected["_http_status"] == 403
    assert rejected["error"]["code"] == "CSRF_REQUIRED"

    redirect = append_message_run(
        {
            "conversation_id": conversation["id"],
            "session_id": "humanop_test",
            "role": "assistant",
            "text": "I am acting as the AI now.",
            "content_format": "text",
            "view": "readable",
            "prompt_view": "original",
            "csrf_token": session["csrf_token"],
        },
        {},
    )
    assert redirect["_redirect"] is True
    assert redirect["status_code"] == 303
    updated = ChatStore().get_conversation(conversation["id"])
    assert updated is not None
    assert updated["messages"][-1]["role"] == "assistant"
    assert updated["messages"][-1]["raw_text"] == "I am acting as the AI now."


def test_human_operator_routes_are_registered():
    from ecosystem.defaultspack.transport.registry import canonical_http_route_specs

    routes = {(spec.method, spec.pattern): spec for spec in canonical_http_route_specs()}

    assert ("GET", "/api/human-operator/conversations/{conversation_id}/sessions/{session_id}") in routes
    assert ("POST", "/api/human-operator/conversations/{conversation_id}/sessions/{session_id}/messages") in routes
