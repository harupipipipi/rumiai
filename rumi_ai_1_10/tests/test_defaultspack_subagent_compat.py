from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace


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


def test_agent_run_subagent_delegate_provider_error_surfaces_safe_text(monkeypatch):
    secret = "sk-subagent-secret"

    def fake_execute(input_data, context):
        return {
            "status": "ok",
            "data": {
                "execution_id": "agent-provider-fail",
                "status": "error",
                "result": {
                    "execution_id": "agent-provider-fail",
                    "status": "error",
                    "error": "provider error: API key " + secret,
                },
            },
        }

    monkeypatch.setattr("blocks.agent.execute.run", fake_execute)

    result = run_subagent_block({"payload": {"task": "delegate this"}}, {})

    assert result["status"] == "ok"
    data = result["data"]
    assert data["status"] == "error"
    assert data["code"] == "DELEGATE_PROVIDER_ERROR"
    assert data["assistant_text"]
    assert data["error"] == data["assistant_text"]
    assert data["delegate"]["status"] == "error"
    assert data["delegate"]["execution_id"] == "agent-provider-fail"
    serialized = json.dumps(data, ensure_ascii=False)
    assert secret not in serialized
    assert "API key" not in serialized


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


def test_tool_subagent_manifest_timeout_is_forwarded_to_capability_executor():
    manifest = json.loads(
        (ROOT / "ecosystem" / "rumi_default_tools_pack" / "tools" / "subagent" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    tool_def = {**manifest["config"], "source_pack_id": "rumi_default_tools_pack"}
    seen: dict[str, object] = {}

    class FakeCapabilityExecutor:
        def execute(self, principal_id, request):
            seen["principal_id"] = principal_id
            seen["request"] = dict(request)
            return SimpleNamespace(
                success=True,
                output={
                    "status": "ok",
                    "data": {
                        "result": "subagent completed",
                        "is_error": False,
                        "widget": {"type": "subagent"},
                    },
                },
                error=None,
                error_type=None,
            )

    result = ToolExecutor()._execute_rumi_function(
        tool_def,
        {"task": "hello from child"},
        {"capability_executor": FakeCapabilityExecutor()},
    )

    assert result["is_error"] is False
    assert seen["principal_id"] == "rumi_default_tools_pack"
    assert seen["request"]["qualified_name"] == "defaultspack:tool_subagent"
    assert seen["request"]["timeout_seconds"] == 240


def test_tool_subagent_defaultspack_function_manifest_keeps_long_timeout():
    from domain.function_runtime.manifest_factory import FUNCTION_SPECS_BY_ID, manifest_for

    generated = manifest_for(FUNCTION_SPECS_BY_ID["tool_subagent"])
    committed = json.loads(
        (ROOT / "ecosystem" / "defaultspack" / "functions" / "tool_subagent" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )

    assert generated["grant_config"]["timeout"] == 240
    assert committed["grant_config"]["timeout"] == 240


def test_tool_subagent_direct_function_call_uses_manifest_timeout(monkeypatch):
    from core_runtime.capability_executor import CapabilityExecutor, CapabilityResponse
    from core_runtime.function_registry import FunctionRegistry

    manifest = json.loads(
        (ROOT / "ecosystem" / "defaultspack" / "functions" / "tool_subagent" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    function_dir = ROOT / "ecosystem" / "defaultspack" / "functions" / "tool_subagent"
    registry = FunctionRegistry()
    assert registry.register(
        pack_id="defaultspack",
        function_id="tool_subagent",
        manifest=manifest,
        function_dir=function_dir,
    )
    seen: dict[str, object] = {}

    class GrantManager:
        def check(self, principal_id, permission_id):
            return SimpleNamespace(allowed=True, reason="Granted", config={})

    class ApprovalManager:
        def is_pack_approved_and_verified(self, pack_id):
            return True

    executor = CapabilityExecutor()
    executor._initialized = True
    executor._function_registry = registry
    executor._grant_manager = GrantManager()
    executor._approval_manager = ApprovalManager()
    executor._permission_manager = SimpleNamespace()
    executor._trust_store = SimpleNamespace()

    monkeypatch.setattr(executor, "_check_entry_trust", lambda entry, permission_id: None)

    def fake_execute_handler_subprocess(**kwargs):
        seen["timeout_seconds"] = kwargs["timeout_seconds"]
        return CapabilityResponse(success=True, output={"status": "ok", "data": {}})

    monkeypatch.setattr(executor, "_execute_handler_subprocess", fake_execute_handler_subprocess)

    response = executor.execute(
        "defaultspack",
        {
            "type": "function.call",
            "qualified_name": "defaultspack:tool_subagent",
            "args": {"task": "hello"},
            "request_id": "req-direct-subagent",
        },
    )

    assert response.success is True
    assert seen["timeout_seconds"] == 240


def test_rumi_default_tools_subagent_compat_uses_dispatcher(monkeypatch, tmp_path):
    _configure_paths(monkeypatch, tmp_path)
    ChatStore._instance = None
    parent = ChatStore().create_conversation(
        model="stub/default",
        system_prompt_id="mimo_coding_company",
        group_id="company:mimo-coding-company",
        metadata={"profile_id": "defaultspack.mimo_coding_company", "company_id": "mimo-coding-company"},
    )
    seen: dict[str, object] = {}

    def fake_dispatch(envelope, context):
        seen["called"] = envelope.target["conversation_id"]
        seen["input"] = envelope.input
        seen["tools"] = envelope.tools
        seen["params"] = envelope.params
        seen["metadata"] = envelope.metadata
        return {"status": "ok", "assistant_text": "done"}

    monkeypatch.setattr("ecosystem.rumi_default_tools_pack.domain.tool.subagent.dispatch_input", fake_dispatch)

    result = SubagentController().run(
        {"task": "delegate this"},
        {
            "conversation_id": parent["id"],
            "model": "stub/default",
            "profile_id": "defaultspack.mimo_coding_company",
            "profile_policy": {"profile_id": "defaultspack.mimo_coding_company"},
            "capability_graph": {"connected_tools": ["todo", "coding_file_search"]},
        },
    )

    assert result["summary"] == "done"
    assert seen["called"]
    assert seen["input"].startswith("Use the connected tools directly.")
    assert seen["tools"] == ["todo", "coding_file_search"]
    assert seen["params"]["tool_policy"]["profile_id"] == "defaultspack.mimo_coding_company"
    assert seen["metadata"]["profile_id"] == "defaultspack.mimo_coding_company"
    child = ChatStore().get_conversation(result["child_conversation_id"])
    assert child["system_prompt_id"] == "mimo_coding_company"
    assert child["group_id"] == "company:mimo-coding-company"
    assert child["metadata"]["profile_id"] == "defaultspack.mimo_coding_company"
    assert child["metadata"]["company_id"] == "mimo-coding-company"


def test_tool_subagent_returns_error_and_marks_child_failed_when_dispatch_times_out(monkeypatch, tmp_path):
    _configure_paths(monkeypatch, tmp_path)
    ChatStore._instance = None
    parent = ChatStore().create_conversation(
        model="stub/default",
        system_prompt_id="mimo_coding_company",
        group_id="company:mimo-coding-company",
        metadata={"profile_id": "defaultspack.mimo_coding_company", "company_id": "mimo-coding-company"},
    )

    def fake_dispatch(envelope, context):
        ChatStore().add_message(
            envelope.target["conversation_id"],
            {
                "role": "user",
                "content": [{"type": "text", "text": envelope.input}],
                "metadata": envelope.metadata,
            },
        )
        raise TimeoutError("handler execution timed out")

    monkeypatch.setattr("ecosystem.rumi_default_tools_pack.domain.tool.subagent.dispatch_input", fake_dispatch)

    result = run_defaultspack_function(
        "tool_subagent",
        {"task": "simple json probe"},
        {"conversation_id": parent["id"]},
    )

    assert result["status"] == "ok"
    assert result["data"]["is_error"] is True
    assert result["data"]["widget"]["type"] == "subagent"
    assert result["data"]["widget"]["child_conversation_id"]
    parent_after = ChatStore().get_conversation(parent["id"])
    child_id = parent_after["child_conversation_ids"][0]
    assert result["data"]["widget"]["child_conversation_id"] == child_id
    child = ChatStore().get_conversation(child_id)
    assert child["metadata"]["subagent"]["status"] == "error"
    assert child["metadata"]["subagent"]["error_code"] == "SUBAGENT_DISPATCH_TIMEOUT"
    assert result["data"]["widget"]["error_type"] == "timeout"
    assert [message["role"] for message in child["messages"]] == ["user", "assistant"]
    assert child["messages"][-1]["finish_reason"] == "error"
    assert "could not complete" in child["messages"][-1]["raw_text"]
    assert "timed out" not in child["messages"][-1]["raw_text"]


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
