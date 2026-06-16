from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


class _ScriptedCallHandler:
    def __init__(self, scripted_outputs):
        self._outputs = list(scripted_outputs)
        self.calls: list[dict] = []

    def __call__(self, handler_id, payload):
        self.calls.append({"handler_id": handler_id, "payload": payload})
        if not self._outputs:
            raise AssertionError("call_handler invoked more times than scripted")
        text = self._outputs.pop(0)
        return {"status": "ok", "data": {"content": text, "model": payload.get("model", "stub")}}


class _DummyManager:
    @staticmethod
    def inject_context_variables(variables, context=None):
        merged = dict(variables or {})
        for key, value in (context or {}).items():
            merged.setdefault("context." + str(key), value)
        return merged


def test_rule_command_pins_lists_and_disables_rule(tmp_path, monkeypatch):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_RULE_STORE_PATH", str(tmp_path / "conversation_rules.json"))

    from blocks.rule.run import run as rule_run
    from domain.chat.rules import ConversationRuleStore

    created = rule_run(
        {
            "conversation_id": "conv_rules",
            "rule": "Keep the work in one pull request.",
            "priority": "high",
        },
        {},
    )

    assert created["status"] == "ok"
    assert created["data"]["created"] is True
    rule = created["data"]["rule"]
    assert rule["immutable_under_compaction"] is True
    assert rule["text"] == "Keep the work in one pull request."

    listed = rule_run({"conversation_id": "conv_rules", "action": "list"}, {})
    assert listed["status"] == "ok"
    assert listed["data"]["total"] == 1
    assert listed["data"]["rules"][0]["id"] == rule["id"]

    prompt_text = ConversationRuleStore().format_for_prompt("conv_rules")
    assert "Keep the work" in prompt_text

    disabled = rule_run(
        {"conversation_id": "conv_rules", "action": "disable", "rule_id": rule["id"]},
        {},
    )
    assert disabled["status"] == "ok"
    assert disabled["data"]["disabled"] is True
    assert ConversationRuleStore().list_rules("conv_rules") == []


def test_rule_records_are_injected_by_context_enrichment(tmp_path, monkeypatch):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_RULE_STORE_PATH", str(tmp_path / "conversation_rules.json"))

    from blocks.chat._context_helpers import enrich_messages
    from domain.chat.rules import ConversationRuleStore

    ConversationRuleStore().create_rule(
        conversation_id="conv_rules",
        text="Always finish the current pull request before opening a follow-up.",
        priority="high",
    )
    messages = [{"role": "user", "content": "continue"}]
    info = enrich_messages(messages, "Base prompt", "conv_rules", "continue", _DummyManager())

    assert "Always finish" in info["rule_text"]
    assert messages[0]["role"] == "system"
    assert "Always finish" in messages[0]["content"]
    assert messages[1]["role"] == "user"


def test_goal_rich_mode_loops_past_default_hard_cap_until_achieved(monkeypatch):
    from blocks.goal import run as goal_module
    from blocks.goal.run import HARD_MAX_ITERATIONS
    from blocks.goal.run import run as goal_run

    scripted = []
    for index in range(HARD_MAX_ITERATIONS + 1):
        achieved = index == HARD_MAX_ITERATIONS
        scripted.append(f"Attempt {index + 1}")
        scripted.append(
            json.dumps(
                {
                    "achieved": achieved,
                    "reason": "done" if achieved else "not yet",
                    "next_instruction": "" if achieved else "continue",
                }
            )
        )

    handler = _ScriptedCallHandler(scripted)

    def fake_call_model(input_data, _context, *, call_handler=None):
        response = call_handler(
            "defaults.ai.complete",
            {
                "model": input_data.get("model_hint") or "stub/default",
                "messages": input_data.get("messages", []),
                "params": {},
            },
        )
        data = response.get("data") if isinstance(response, dict) and response.get("status") == "ok" else response
        text = data.get("content", "") if isinstance(data, dict) else ""
        if input_data.get("output_schema"):
            return {"status": "ok", "output": json.loads(text)}
        return {"status": "ok", "output": text}

    monkeypatch.setattr(goal_module, "call_model", fake_call_model)

    result = goal_run(
        {
            "goal": "/rich Solve the long goal",
            "max_iterations": "rich",
        },
        {"call_handler": handler},
    )

    assert result["status"] == "ok"
    data = result["data"]
    assert data["mode"] == "rich"
    assert data["rich"] is True
    assert data["hard_cap"] is None
    assert data["max_iterations"] is None
    assert data["goal"] == "Solve the long goal"
    assert data["achieved"] is True
    assert data["iteration_count"] == HARD_MAX_ITERATIONS + 1
    assert data["iteration_count"] > HARD_MAX_ITERATIONS
    assert data["stopped_reason"] == "achieved"
