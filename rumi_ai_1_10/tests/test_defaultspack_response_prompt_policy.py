from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.external.input_profile import InputProfile  # noqa: E402
from domain.external.event import ExternalEvent  # noqa: E402
from domain.external.adapters.discord import DiscordResponseAdapter  # noqa: E402
from domain.external.adapters.line import LineResponseAdapter  # noqa: E402
from domain.external.response import RumiResponse  # noqa: E402
from domain.external.response_planner import ResponsePlanner  # noqa: E402
from domain.external.response_prompt_policy import ResponsePromptDecision, ResponsePromptPolicy  # noqa: E402


BASE_ALLOWED_ACTIONS = [
    "reply_text",
    "store_only",
    "summarize_then_reply",
    "run_browser_use",
    "run_computer_use",
    "run_python",
    "run_tool",
    "send_file_if_allowed",
    "ask_for_approval",
]


def _event(provider: str = "discord") -> dict[str, Any]:
    return {
        "provider": provider,
        "workspace": {"type": "workspace", "id": "w1"},
        "scope": {"type": "channel", "id": "c1"},
        "actor": {"type": "user", "id": "u1"},
        "conversation": {"type": "channel", "id": "c1"},
        "event": {"id": "e1", "type": "message"},
        "payload": {},
        "verified": True,
    }


def _config(**overrides: Any) -> dict[str, Any]:
    config = {
        "enabled": True,
        "mode": "plan_only",
        "allowed_actions": list(BASE_ALLOWED_ACTIONS),
        "fallback_action": "reply_text",
        "tools": {},
    }
    config.update(overrides)
    return config


def _policy(config: dict[str, Any]) -> ResponsePromptPolicy:
    profile = InputProfile.from_dict(
        {
            "id": "test.profile",
            "provider": "discord",
            "version": 1,
            "display_name": "Test profile",
            "response_prompt": config,
        }
    )
    return ResponsePromptPolicy.from_profile(profile)


def _decision(
    llm_payload: Any,
    *,
    config: dict[str, Any] | None = None,
    provider: str = "discord",
    response: RumiResponse | None = None,
) -> ResponsePromptDecision:
    policy = _policy(config or _config())
    return policy.decide(
        _event(provider),
        input_text="hello",
        response=response or RumiResponse(text="assistant reply"),
        llm_client=lambda payload: llm_payload,
    )


def _plan(decision: ResponsePromptDecision, *, provider: str = "discord", response: RumiResponse | None = None) -> dict[str, Any]:
    return ResponsePlanner(provider).plan(response or RumiResponse(text="assistant reply"), prompt_decision=decision)


def test_reply_text_returns_external_message():
    decision = _decision({"action": "reply_text", "reason": "answer directly"})
    plan = _plan(decision)

    assert decision.action == "reply_text"
    assert plan["messages"] == [{"type": "text", "text": "assistant reply"}]
    assert plan["metadata"]["response_action_plan"]["type"] == "reply"
    assert plan["metadata"]["response_action_plan"]["external_reply"] is True


def test_store_only_suppresses_external_messages_files_and_marks_action_plan():
    decision = _decision({"action": "store_only", "reason": "internal note"})
    response = RumiResponse(
        text="do not send",
        artifacts=[{"path": "/tmp/a.txt", "mime_type": "text/plain", "size": 10}],
    )
    plan = _plan(decision, response=response)

    assert plan["messages"] == []
    assert plan["files"] == []
    assert plan["metadata"]["response_action_plan"]["type"] == "store_only"
    assert plan["metadata"]["response_action_plan"]["external_reply"] is False


def test_run_python_enabled_becomes_tool_followup_without_approval():
    decision = _decision(
        {"action": "run_python", "instruction": "calculate it"},
        config=_config(tools={"python": {"enabled": True}}),
    )
    plan = _plan(decision)
    action_plan = plan["metadata"]["response_action_plan"]

    assert decision.action == "run_python"
    assert decision.requires_approval is False
    assert decision.executable is True
    assert action_plan["type"] == "tool_followup"
    assert action_plan["tool"] == "python"
    assert action_plan["requires_approval"] is False
    assert plan["messages"] == []


def test_run_browser_use_enabled_becomes_tool_followup():
    decision = _decision(
        {"action": "run_browser_use", "instruction": "open the page"},
        config=_config(tools={"browser_use": {"enabled": True}}),
    )
    plan = _plan(decision)
    action_plan = plan["metadata"]["response_action_plan"]

    assert decision.action == "run_browser_use"
    assert decision.requires_approval is False
    assert action_plan["type"] == "tool_followup"
    assert action_plan["tool"] == "browser_use"
    assert action_plan["requires_approval"] is False
    assert plan["messages"] == []


def test_run_tool_can_plan_external_send_without_executing_it():
    decision = _decision(
        {
            "action": "run_tool",
            "tool": "external_send",
            "instruction": "Send the short result to Discord.",
            "output": {"provider": "discord", "output_profile_id": "discord.bot_channel"},
        },
        config=_config(tools={"external_send": {"enabled": True, "requires_approval": True}}),
    )
    plan = _plan(decision)
    action_plan = plan["metadata"]["response_action_plan"]

    assert decision.action == "run_tool"
    assert decision.tool_name == "external_send"
    assert decision.requires_approval is True
    assert action_plan["type"] == "tool_followup"
    assert action_plan["tool"] == "external_send"
    assert action_plan["external_reply"] is False
    assert action_plan["output"]["output_profile_id"] == "discord.bot_channel"
    assert plan["messages"] == []


def test_output_target_not_in_allowed_outputs_falls_back():
    decision = _decision(
        {
            "action": "reply_text",
            "output": {"provider": "discord", "output_profile_id": "discord.bot_channel"},
        },
        config=_config(allowed_outputs=["line.default"]),
        response=RumiResponse(text="fallback text"),
    )

    assert decision.action == "reply_text"
    assert decision.fallback is True
    assert decision.reason == "output target not allowed"
    assert decision.metadata["rejected_output"]["provider"] == "discord"


def test_run_computer_use_enabled_defaults_to_approval_gated_plan():
    decision = _decision(
        {"action": "run_computer_use", "instruction": "click the button"},
        config=_config(tools={"computer_use": {"enabled": True}}),
    )
    plan = _plan(decision)
    action_plan = plan["metadata"]["response_action_plan"]

    assert decision.action == "run_computer_use"
    assert decision.requires_approval is True
    assert decision.executable is False
    assert action_plan["type"] == "tool_followup"
    assert action_plan["tool"] == "computer_use"
    assert action_plan["requires_approval"] is True
    assert action_plan["external_reply"] is False
    assert plan["messages"] == []


def test_action_not_in_allowed_actions_falls_back_to_reply_text():
    decision = _decision(
        {"action": "run_python", "instruction": "calculate it"},
        config=_config(allowed_actions=["reply_text"]),
        response=RumiResponse(text="fallback text"),
    )
    plan = _plan(decision, response=RumiResponse(text="fallback text"))

    assert decision.action == "reply_text"
    assert decision.fallback is True
    assert decision.reason == "action not allowed"
    assert decision.metadata["rejected_action"] == "run_python"
    assert plan["messages"] == [{"type": "text", "text": "fallback text"}]


def test_invalid_json_falls_back_to_reply_text():
    decision = _decision("{not valid json", response=RumiResponse(text="fallback text"))
    plan = _plan(decision, response=RumiResponse(text="fallback text"))

    assert decision.action == "reply_text"
    assert decision.fallback is True
    assert decision.reason == "invalid json"
    assert plan["messages"] == [{"type": "text", "text": "fallback text"}]


def test_local_only_sensitivity_suppresses_external_reply():
    decision = _decision({"action": "reply_text", "sensitivity": "local_only"})
    plan = _plan(decision)

    assert decision.sensitivity == "local_only"
    assert decision.sends_external_reply is False
    assert plan["messages"] == []
    assert plan["files"] == []
    assert plan["metadata"]["response_action_plan"]["type"] == "store_only"
    assert plan["metadata"]["response_action_plan"]["external_reply"] is False


def test_discord_chunking_and_safe_defaults_survive_reply_text_policy():
    decision = _decision(json.dumps({"action": "reply_text"}))
    plan = _plan(decision, response=RumiResponse(text="a" * 2500))

    assert len(plan["messages"]) == 2
    assert len(plan["messages"][0]["text"]) == 2000
    assert len(plan["messages"][1]["text"]) == 500
    assert plan["safe_defaults"]["allowed_mentions"] == {"parse": []}
    assert plan["metadata"]["response_prompt_decision"]["action"] == "reply_text"


def test_line_files_disabled_with_send_file_if_allowed_uses_existing_planner_fallback():
    decision = _decision({"action": "send_file_if_allowed"}, provider="line")
    plan = _plan(
        decision,
        provider="line",
        response=RumiResponse(
            text="ok",
            artifacts=[{"path": "/tmp/a.txt", "mime_type": "text/plain", "size": 10}],
        ),
    )

    assert plan["messages"] == [{"type": "text", "text": "ok"}]
    assert plan["files"] == []
    assert plan["fallbacks"][0]["reason"] == "files disabled"
    assert plan["safe_defaults"] == {"supports_reply_token": True, "supports_push": True}


def test_pipeline_does_not_run_response_prompt_policy_when_send_response_false(monkeypatch):
    from domain.external import pipeline  # noqa: E402

    profile = InputProfile.from_dict(
        {
            "id": "prompt.enabled",
            "provider": "discord",
            "version": 1,
            "display_name": "Prompt Enabled",
            "match": {"event_type": "message"},
            "input": {"role": "user", "content": "$.content"},
            "metadata": {"source": {"kind": "integration", "provider": "discord"}},
            "response_prompt": {"enabled": True, "allowed_actions": ["reply_text"]},
        }
    )

    class FakeRegistry:
        def get(self, _profile_id):
            return profile

    def fail_if_called(_payload):
        raise AssertionError("response prompt llm should not run")

    monkeypatch.setattr(pipeline, "InputProfileRegistry", FakeRegistry)
    monkeypatch.setattr(pipeline, "submit_input", lambda envelope, context: {"status": "ok", "assistant_text": "done"})

    result = pipeline.dispatch_external_event(
        ExternalEvent.from_dict(_event()),
        input_profile_id="prompt.enabled",
        context={"response_prompt_llm": fail_if_called},
        send_response=False,
    )

    assert result["status"] == "ok"
    assert "response_prompt_decision" not in result
    assert "response_plan" not in result


def test_pipeline_merges_input_profile_policy_into_runtime_context(monkeypatch):
    from domain.external import pipeline  # noqa: E402

    profile = InputProfile.from_dict(
        {
            "id": "line.computer_use",
            "provider": "line",
            "version": 1,
            "display_name": "LINE Computer Use",
            "match": {"event_type": "message"},
            "input": {"role": "user", "content": "$.message.text"},
            "metadata": {"source": {"kind": "integration", "provider": "line"}},
            "policy": {"max_tool_calls": 30},
        }
    )

    class FakeRegistry:
        def get(self, _profile_id):
            return profile

    captured = {}

    def fake_submit_input(envelope, context):
        captured["envelope"] = envelope
        captured["context"] = context
        return {"status": "ok", "assistant_text": "done"}

    monkeypatch.setattr(pipeline, "InputProfileRegistry", FakeRegistry)
    monkeypatch.setattr(pipeline, "submit_input", fake_submit_input)

    result = pipeline.dispatch_external_event(
        ExternalEvent.from_dict(
            {
                "provider": "line",
                "workspace": {"type": "line_destination", "id": "Udest"},
                "scope": {"type": "user", "id": "U123"},
                "actor": {"type": "user", "id": "U123"},
                "conversation": {"type": "external", "id": "line:user:U123"},
                "event": {"id": "evt-1", "type": "message", "message_type": "text"},
                "payload": {
                    "type": "message",
                    "message": {"id": "m1", "type": "text", "text": "open chrome"},
                    "source": {"type": "user", "userId": "U123"},
                    "replyToken": "reply-1",
                },
                "verified": True,
                "metadata": {"model": "google/gemma-4-31b-it"},
            }
        ),
        input_profile_id="line.computer_use",
        context={"profile_policy": {"yolo_mode": True}},
        send_response=False,
    )

    assert result["status"] == "ok"
    assert captured["context"]["profile_policy"]["max_tool_calls"] == 30
    assert captured["context"]["profile_policy"]["yolo_mode"] is True


def test_adapters_recheck_suppressed_external_reply_before_sending():
    plan = {
        "messages": [{"type": "text", "text": "do not send"}],
        "metadata": {
            "response_action_plan": {"type": "store_only", "external_reply": False},
            "response_prompt_decision": {"action": "store_only", "sensitivity": "local_only"},
        },
    }

    assert LineResponseAdapter().send(plan)["sent"] is False
    assert DiscordResponseAdapter().send(plan)["sent"] is False


def test_discord_interaction_uses_deferred_response_when_external_reply_is_suppressed(monkeypatch):
    from blocks.integrations import discord as discord_block  # noqa: E402

    monkeypatch.setattr(discord_block, "_verify_discord", lambda headers, raw_body: {"ok": True, "verified": True})
    monkeypatch.setattr(
        discord_block,
        "_handle_interaction",
        lambda input_data, context, verified=False: {
            "assistant_text": "hidden",
            "response_plan": {
                "messages": [],
                "metadata": {"response_action_plan": {"type": "store_only", "external_reply": False}},
            },
        },
    )

    result = discord_block.run({"type": discord_block.DISCORD_APPLICATION_COMMAND}, {})

    assert result["type"] == discord_block.DISCORD_DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE
    assert "data" not in result
