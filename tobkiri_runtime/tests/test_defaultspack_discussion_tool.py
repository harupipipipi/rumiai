from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_discussion_tool_uses_history_role_and_returns_unanimous_report(
    monkeypatch,
):
    from domain.ai_client.client import AIClient
    from domain.tool.discussion import run_discussion

    prompts = []
    events = []

    def fake_complete(self, model, messages, tools=None, params=None):
        del self, tools
        system = str(messages[0]["content"])
        prompt = str(messages[-1]["content"])
        prompts.append(
            {
                "model": model,
                "system": system,
                "prompt": prompt,
                "params": dict(params or {}),
            }
        )
        if "Design a balanced discussion panel" in system:
            payload = {
                "perspectives": [
                    {"id": "positive", "name": "Positive", "mission": "Find value"},
                    {"id": "critical", "name": "Critical", "mission": "Find failure"},
                    {"id": "user", "name": "User", "mission": "Check explicit needs"},
                ]
            }
        elif "Act as each assigned perspective" in system:
            perspective_items = json.loads(prompt)["perspectives"]
            payload = {
                "opinions": [
                    {
                        "perspective_id": item["id"],
                        "position": "Useful with safeguards",
                        "arguments": ["Reason"],
                        "risks": ["Risk"],
                        "required_changes": [],
                    }
                    for item in perspective_items
                ]
            }
        elif "Synthesize a decision-quality report" in system:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "# Report\n\nBalanced conclusion.",
                    }
                ]
            }
        else:
            perspective_items = json.loads(prompt)["perspectives"]
            payload = {
                "verdicts": [
                    {
                        "perspective_id": item["id"],
                        "perfect": True,
                        "issues": [],
                    }
                    for item in perspective_items
                ]
            }
        return {"content": [{"type": "text", "text": json.dumps(payload)}]}

    monkeypatch.setattr(AIClient, "complete", fake_complete)
    result = run_discussion(
        {"topic": "Should we ship this feature?"},
        {
            "conversation_model": "demo/conversation-model",
            "agent_role": "You are a release manager.",
            "agent_conversation_history": [
                {"role": "user", "content": "Reliability is the priority."}
            ],
            "stream_event_callback": events.append,
        },
    )

    assert result["is_error"] is False
    payload = json.loads(result["result"])
    assert payload["status"] == "perfect"
    assert payload["iterations"] == 1
    assert payload["report"].startswith("# Report")
    assert set(payload["model"].values()) == {
        "demo/conversation-model"
    }
    assert {item["id"] for item in payload["perspectives"]} == {
        "affirmative",
        "positive",
        "critical",
        "user",
    }
    assert "release manager" in prompts[0]["prompt"]
    assert "Reliability is the priority" in prompts[0]["prompt"]
    assert {prompt["model"] for prompt in prompts} == {
        "demo/conversation-model"
    }
    assert "response_format" not in prompts[0]["params"]
    assert any(event.get("discussion_phase") == "completed" for event in events)


def test_discussion_flow_contract_is_declarative_and_bounded():
    from ecosystem.defaultspack.domain.flow import FlowEngine

    FlowEngine.reset_instance()
    engine = FlowEngine()
    flow = engine.get_flow("defaultspack.discussion")

    assert engine.validate_flow("defaultspack.discussion") == []
    loop = next(step for step in flow["steps"] if step["type"] == "loop")
    assert loop["max_iterations"] == 4
    assert loop["until"] == "{{consensus.perfect}}"
    assert loop["dedupe_key"] == "{{consensus.report_hash}}"


def test_discussion_is_selected_by_default_but_respects_explicit_disable():
    from domain.chat.run_request import (
        NormalizedToolSelection,
        _with_default_discussion_selection,
    )
    from domain.chat.tool_selection_schema import normalize_tool_target

    enabled = _with_default_discussion_selection(
        NormalizedToolSelection(),
        available=True,
    )
    assert [(item.kind, item.id) for item in enabled.include] == [
        ("tool", "discussion")
    ]
    disabled = _with_default_discussion_selection(
        NormalizedToolSelection(
            exclude=[normalize_tool_target("discussion")],
        ),
        available=True,
    )
    assert disabled.include == []
    none_mode = _with_default_discussion_selection(
        NormalizedToolSelection(mode="none"),
        available=True,
    )
    assert none_mode.include == []


def test_discussion_repairs_invalid_model_json_once():
    from domain.tool.discussion import _call_json

    class Client:
        def __init__(self):
            self.calls = 0

        def complete(self, model, messages, tools, params):
            del model, messages, tools, params
            self.calls += 1
            text = "not json" if self.calls == 1 else '{"perfect": true}'
            return {"content": [{"type": "text", "text": text}]}

    client = Client()
    assert _call_json(
        client,
        "demo/any-model",
        system="Return JSON.",
        prompt='{"schema":{"perfect":true}}',
    ) == {"perfect": True}
    assert client.calls == 2


def test_discussion_accepts_public_markdown_with_unescaped_newlines():
    from domain.tool.discussion import _json_object

    assert _json_object(
        'Result follows:\n{"report":"# Decision\n\nProceed gradually.",'
        '"agreements":["Safety",],}\nEnd.'
    ) == {
        "report": "# Decision\n\nProceed gradually.",
        "agreements": ["Safety"],
    }


def test_discussion_synthesis_has_deterministic_empty_model_fallback(monkeypatch):
    from domain.tool import discussion

    monkeypatch.setattr(discussion, "_call_text", lambda *args, **kwargs: "")
    adapter = discussion._DiscussionFlowAdapter(
        {"conversation_model": "demo/conversation-model"}
    )
    result = adapter.synthesize(
        {
            "topic": "Staged rollout",
            "iteration": 1,
            "opinions": {
                "items": [
                    {
                        "perspective": {"name": "Critical"},
                        "position": "Proceed only with rollback.",
                        "required_changes": ["Define stop conditions."],
                    }
                ]
            },
        }
    )
    assert result["report"].startswith("# Discussion report")
    assert "Proceed only with rollback." in result["report"]
    assert result["disagreements"] == ["Define stop conditions."]
