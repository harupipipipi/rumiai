from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from blocks.agent.run_subagent import run as run_subagent_block  # noqa: E402
from domain.chat.store import ChatStore  # noqa: E402
from domain.function_runtime.dispatcher import run_defaultspack_function  # noqa: E402
from domain.tool.executor import ToolExecutor  # noqa: E402
from ecosystem.rumi_default_tools_pack.domain.tool.subagent import SubagentController  # noqa: E402


def _configure_paths(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(tmp_path / "chat" / "conversations.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_INTEGRATIONS_STORE_PATH", str(tmp_path / "integrations" / "conversations.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_INTEGRATIONS_LOCKS_DIR", str(tmp_path / "integrations" / "event_locks"))
    ChatStore._instance = None


def _parent_conversation() -> dict:
    ChatStore._instance = None
    return ChatStore().create_conversation(model="stub/default")


def test_legacy_run_subagent_wrapper_uses_dispatcher_or_delegate(monkeypatch):
    seen: dict[str, object] = {}

    def fake_call_model(*args, **kwargs):
        seen["called"] = True
        return {"status": "ok", "output": {"recommended_tools": [{"tool_id": "search_docs"}]}}

    monkeypatch.setattr("domain.agent.subagent_orchestrator.call_model", fake_call_model)

    result = run_subagent_block({"role_id": "tool_selector", "payload": {"candidate_tools": [{"tool_id": "search_docs"}]}}, {"call_handler": object()})

    assert result["status"] == "ok"
    assert seen["called"] is True


def test_agent_run_subagent_compat_routes_to_delegate_or_utility(monkeypatch):
    monkeypatch.setattr(
        "domain.agent.subagent_orchestrator.call_model",
        lambda *args, **kwargs: {"status": "ok", "output": {"recommended_tools": [{"tool_id": "search_docs"}]}},
    )

    result = run_defaultspack_function(
        "agent_run_subagent",
        {"role_id": "tool_selector", "payload": {"candidate_tools": [{"tool_id": "search_docs"}]}},
        {"call_handler": object()},
    )

    assert result["status"] == "ok"
    assert result["data"]["output"]["recommended_tools"][0]["tool_id"] == "search_docs"


def test_agent_run_subagent_compat_task_payload_routes_through_agent_delegate(monkeypatch):
    seen: dict[str, object] = {}

    def fake_dispatch(envelope, context):
        seen["action_id"] = envelope.delivery.get("action_id")
        seen["input"] = envelope.input
        seen["conversation_id"] = envelope.target.get("conversation_id")
        return {"status": "ok", "delegate": {"execution_id": "run_1"}, "result": {"status": "queued"}}

    monkeypatch.setattr("domain.input.dispatcher.dispatch_input", fake_dispatch)

    result = run_subagent_block(
        {"role_id": "delegate", "payload": {"task": "delegate this", "tools": ["browser"]}},
        {"conversation_id": "conv_1"},
    )

    assert result["status"] == "ok"
    assert seen["action_id"] == "agent.delegate"
    assert seen["input"] == "delegate this"
    assert seen["conversation_id"] == "conv_1"


def test_tool_subagent_compat_returns_structured_result(monkeypatch, tmp_path):
    _configure_paths(monkeypatch, tmp_path)
    parent = _parent_conversation()
    monkeypatch.setattr(
        "blocks.chat.send.run",
        lambda request, context: {
            "status": "ok",
            "data": {"id": "assistant-1", "content": [{"type": "text", "text": "done"}]},
        },
    )

    result = run_defaultspack_function(
        "tool_subagent",
        {"task": "hello from child"},
        {"conversation_id": parent["id"], "model": "stub/default"},
    )

    assert result["status"] == "ok"
    assert result["data"]["widget"]["type"] == "subagent"


def test_rumi_default_tools_subagent_compat_uses_dispatcher(monkeypatch, tmp_path):
    _configure_paths(monkeypatch, tmp_path)
    parent = _parent_conversation()
    seen: dict[str, object] = {}

    def fake_dispatch(envelope, context):
        seen["called"] = envelope.target["conversation_id"]
        return {"status": "ok", "assistant_text": "done"}

    monkeypatch.setattr("ecosystem.rumi_default_tools_pack.domain.tool.subagent.dispatch_input", fake_dispatch)

    result = SubagentController().run({"task": "delegate this"}, {"conversation_id": parent["id"], "model": "stub/default"})

    assert result["summary"] == "done"
    assert seen["called"]


def test_tool_selector_no_longer_depends_on_special_subagent_only_path(monkeypatch):
    seen: dict[str, object] = {}

    def fake_model_call(*args, **kwargs):
        seen["called"] = True
        return {"status": "ok", "output": {"recommended_tools": [{"tool_id": "search_docs", "confidence": 0.9, "reason": "fits"}]}}

    monkeypatch.setattr("domain.chat.tool_selection_orchestrator.call_model", fake_model_call)

    from domain.chat.tool_selection_orchestrator import ToolSelectionOrchestrator

    result = ToolSelectionOrchestrator().select(
        "search docs",
        [{"tool_id": "search_docs", "summary": "Search docs"}],
        selected_model_capabilities={"supports_tool_calling": True},
    )

    assert seen["called"] is True
    assert result["recommended_tools"][0]["tool_id"] == "search_docs"


def test_docs_do_not_present_subagent_as_primary_architecture():
    source = (ROOT / "docs" / "subagents.md").read_text(encoding="utf-8").lower()
    functions_doc = (ROOT / "docs" / "defaultspack-functions.md").read_text(encoding="utf-8").lower()

    assert "compatibility" in source
    assert "no longer treats \"subagent\" as a primary architecture concept" in source
    assert "utility subagents" not in functions_doc


def test_multi_agent_boundary_documented_and_not_broken():
    source = (ROOT / "docs" / "subagents.md").read_text(encoding="utf-8")

    assert "agent.delegate" in source
    assert "multi-agent" in source


def test_subagent_alias_does_not_bypass_tool_policy_or_approval():
    result = ToolExecutor().execute(
        "subagent",
        {"task": "hello"},
        {"profile_policy": {"disabled_tools": ["subagent"]}},
    )

    assert result["is_error"] is True
    assert result["rejected_by_policy"] is True
