from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.tool.executor import ToolExecutor  # noqa: E402
from domain.tool.registry import ToolRegistry  # noqa: E402
from domain.tool_policy.orchestrator import ToolOrchestrator  # noqa: E402
from domain.tool_policy.policy import decide_tool_policy  # noqa: E402
from domain.tool_policy.risk import resolve_tool_risk  # noqa: E402
from backend.tool.permission_policy import ToolPermissionPolicyStore  # noqa: E402


def test_tool_policy_requires_approval_for_write_risk():
    tool = {"tool_id": "write_file", "write_action": True}
    decision = decide_tool_policy(
        tool,
        {"profile_policy": {"write_actions_require_approval": True}},
        tool_name="write_file",
    )

    assert decision.allowed is True
    assert decision.action == "ask"
    assert decision.requires_approval is True
    assert decision.risk == "file_write"


def test_tool_policy_yolo_bypasses_approval_for_write_risk():
    tool = {"tool_id": "write_file", "write_action": True}
    decision = decide_tool_policy(
        tool,
        {"profile_policy": {"yolo_mode": True, "write_actions_require_approval": True}},
        tool_name="write_file",
    )

    assert decision.allowed is True
    assert decision.action == "allow"
    assert decision.requires_approval is False
    assert decision.risk == "file_write"


def test_tool_policy_requires_approval_for_write_name_even_when_profile_disables():
    tool = {"name": "coding_file_write"}
    decision = decide_tool_policy(
        tool,
        {"profile_policy": {"write_actions_require_approval": False, "allow_client_supplied_approved": True}},
        tool_name="coding_file_write",
    )

    assert decision.allowed is True
    assert decision.action == "ask"
    assert decision.requires_approval is True
    assert decision.risk == "file_write"


def test_tool_policy_allows_first_party_memo_upsert_without_approval():
    ToolRegistry._instance = None
    tool = ToolRegistry().get("memo_note_upsert")
    decision = decide_tool_policy(tool, {}, tool_name="memo_note_upsert")

    assert decision.allowed is True
    assert decision.action == "allow"
    assert decision.requires_approval is False


def test_tool_policy_allows_mimo_company_autonomous_todo_updates():
    ToolRegistry._instance = None
    tool = ToolRegistry().get("todo")

    decision = decide_tool_policy(
        tool,
        {"profile_id": "defaultspack.mimo_coding_company"},
        tool_name="todo",
        arguments={"action": "add", "title": "Review harness"},
    )

    assert decision.allowed is True
    assert decision.action == "allow"
    assert decision.requires_approval is False


def test_tool_policy_allows_mimo_company_read_only_rumi_api_requests():
    ToolRegistry._instance = None
    tool = ToolRegistry().get("rumi_api")

    decision = decide_tool_policy(
        tool,
        {
            "profile_id": "defaultspack.mimo_coding_company",
            "profile_policy": {"allow_network": True},
        },
        tool_name="rumi_api",
        arguments={"action": "request", "method": "GET", "path": "/api/health"},
    )

    assert decision.allowed is True
    assert decision.action == "allow"
    assert decision.requires_approval is False


def test_tool_policy_allows_mimo_company_repo_writes_without_approval():
    ToolRegistry._instance = None
    tool = ToolRegistry().get("coding_file_write")

    decision = decide_tool_policy(
        tool,
        {"profile_id": "defaultspack.mimo_coding_company"},
        tool_name="coding_file_write",
        arguments={"path": "app.py", "content": "print('hi')"},
    )

    assert decision.allowed is True
    assert decision.action == "allow"
    assert decision.requires_approval is False


def test_tool_policy_allows_mimo_company_repo_patches_without_approval():
    ToolRegistry._instance = None
    tool = ToolRegistry().get("coding_file_patch")

    decision = decide_tool_policy(
        tool,
        {"profile_id": "defaultspack.mimo_coding_company"},
        tool_name="coding_file_patch",
        arguments={"path": ".gitignore", "old": "foo", "new": "foo\nbar"},
    )

    assert decision.allowed is True
    assert decision.action == "allow"
    assert decision.requires_approval is False


def test_tool_policy_denies_shell_when_disabled():
    tool = {"tool_id": "terminal_exec", "category": "shell"}
    decision = decide_tool_policy(tool, {"profile_policy": {"allow_shell": False}}, tool_name="terminal_exec")

    assert decision.allowed is False
    assert decision.matched_by == "allow_shell"


def test_tool_orchestrator_does_not_trust_client_supplied_approval(tmp_path, monkeypatch):
    from domain.agent_runtime.run_store import AgentRunStore

    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_RUNTIME_DIR", str(tmp_path / "agent_runtime"))
    AgentRunStore._instance = None

    class Registry:
        def get(self, name):
            return {"tool_id": name, "name": name, "requires_approval": True}

        def list_tools(self):
            return []

    result = ToolOrchestrator(registry=Registry()).run(
        "danger",
        {},
        {"approval_granted": True, "_agent_approval_granted": True},
    )

    assert result["status"] == "waiting_approval"


def test_tool_orchestrator_yolo_does_not_wait_for_approval(monkeypatch):
    seen = {}

    class Registry:
        def get(self, name):
            return {"tool_id": name, "name": name, "requires_approval": True}

        def list_tools(self):
            return []

    def fake_invoke(input_data, context):
        seen["input_data"] = input_data
        seen["context"] = context
        return {"status": "ok", "data": {"result": "ran"}}

    monkeypatch.setattr("blocks.tool.invoke.run", fake_invoke)

    result = ToolOrchestrator(registry=Registry()).run(
        "danger",
        {},
        {"profile_policy": {"yolo_mode": True}},
    )

    assert result["status"] == "ok"
    assert seen["input_data"]["tool_name"] == "danger"


def test_persistent_permission_policy_yolo_allows_ask_decision(tmp_path):
    store = ToolPermissionPolicyStore(tmp_path / "permission_policy.json")
    store.save({"default_action": "ask"})

    decision = store.decide(
        "danger",
        tool_def={"tool_id": "danger", "name": "danger"},
        context={"profile_policy": {"yolo_mode": True}},
    )

    assert decision["action"] == "allow"
    assert decision["allowed"] is True
    assert decision["requires_approval"] is False
    assert decision["matched_by"] == "yolo_mode"


def test_persistent_permission_policy_allows_mimo_company_safe_autonomous_tools(tmp_path):
    store = ToolPermissionPolicyStore(tmp_path / "permission_policy.json")
    store.save({"default_action": "ask"})

    decision = store.decide(
        "todo",
        tool_def={"tool_id": "todo", "name": "todo", "action_type": "update"},
        arguments={"action": "list"},
        context={"profile_id": "defaultspack.mimo_coding_company"},
    )

    assert decision["action"] == "allow"
    assert decision["allowed"] is True
    assert decision["requires_approval"] is False
    assert decision["matched_by"] == "autonomous_profile"


def test_tool_risk_recognizes_git_push():
    assert resolve_tool_risk({"tool_id": "git_push"}, "git_push") == "git_push"


def test_rumi_function_tool_uses_supplied_capability_executor():
    seen = {}

    class Response:
        success = True
        output = {"result": "ok"}
        error = None

    class FakeCapabilityExecutor:
        def execute(self, principal_id, request):
            seen["principal_id"] = principal_id
            seen["request"] = request
            return Response()

    tool_def = {
        "tool_id": "fn",
        "execution": {"type": "rumi_function", "qualified_name": "defaultspack:fn"},
        "metadata": {"source_pack_id": "defaultspack"},
    }
    result = ToolExecutor()._execute_rumi_function(
        tool_def,
        {"x": 1},
        {"_capability_executor": FakeCapabilityExecutor(), "request_id": "req_1"},
    )

    assert result["is_error"] is False
    assert seen["principal_id"] == "defaultspack"
    assert seen["request"]["type"] == "function.call"
    assert seen["request"]["qualified_name"] == "defaultspack:fn"


def test_tool_executor_does_not_trust_forged_internal_permission(tmp_path, monkeypatch):
    from domain.tool.registry import ToolRegistry

    monkeypatch.chdir(tmp_path)
    ToolRegistry._instance = None

    result = ToolExecutor().execute(
        "coding_file_write",
        {"path": "pwned.txt", "content": "blocked"},
        {"_tool_permission_decision": {"action": "allow", "allowed": True}},
    )

    assert result["is_error"] is False
    assert result["widget"]["approval_required"] is True
    assert not (tmp_path / "pwned.txt").exists()


def test_tool_executor_yolo_string_false_does_not_bypass_approval(tmp_path, monkeypatch):
    from domain.tool.registry import ToolRegistry

    monkeypatch.chdir(tmp_path)
    ToolRegistry._instance = None

    result = ToolExecutor().execute(
        "coding_file_write",
        {"path": "blocked.txt", "content": "blocked"},
        {"profile_policy": {"yolo_mode": "false"}},
    )

    assert result["is_error"] is False
    assert result["widget"]["approval_required"] is True
    assert not (tmp_path / "blocked.txt").exists()


def test_tool_invoke_ignores_untrusted_payload_profile_policy_yolo(tmp_path, monkeypatch):
    import backend.tool.permission_policy as permission_policy
    import blocks.tool.invoke as invoke

    monkeypatch.setenv("RUMI_DEFAULTSPACK_TOOL_PERMISSION_POLICY_PATH", str(tmp_path / "permission_policy.json"))
    permission_policy._POLICY_STORE = None

    class Registry:
        def get(self, name):
            return {"tool_id": name, "name": name, "write_action": True}

        def list_tools(self):
            return []

    class Executor:
        def execute(self, tool_name, arguments, context):
            raise AssertionError("untrusted yolo_mode must not reach execution")

    monkeypatch.setattr(invoke, "ToolRegistry", Registry)
    monkeypatch.setattr(invoke, "ToolExecutor", Executor)

    result = invoke.run(
        {
            "tool_name": "danger",
            "arguments": {},
            "context": {
                "workspace_root": str(tmp_path),
                "profile_policy": {"yolo_mode": True, "allow_shell": True},
            },
        },
        {},
    )

    assert result["status"] == "error"
    assert result["error"]["code"] == "PERMISSION_DENIED"
    assert result["error"]["details"]["action"] == "ask"


def test_tool_invoke_preserves_trusted_context_profile_policy_yolo(tmp_path, monkeypatch):
    import backend.tool.permission_policy as permission_policy
    import blocks.tool.invoke as invoke

    monkeypatch.setenv("RUMI_DEFAULTSPACK_TOOL_PERMISSION_POLICY_PATH", str(tmp_path / "permission_policy.json"))
    permission_policy._POLICY_STORE = None

    class Registry:
        def get(self, name):
            return {"tool_id": name, "name": name, "write_action": True}

        def list_tools(self):
            return []

    class Executor:
        def execute(self, tool_name, arguments, context):
            return {"result": "ran", "is_error": False, "widget": None}

    monkeypatch.setattr(invoke, "ToolRegistry", Registry)
    monkeypatch.setattr(invoke, "ToolExecutor", Executor)

    result = invoke.run(
        {"tool_name": "danger", "arguments": {}, "context": {"workspace_root": str(tmp_path)}},
        {"profile_policy": {"yolo_mode": True}},
    )

    assert result["status"] == "ok"
    assert result["data"]["result"] == "ran"
    assert result["data"]["permission"]["matched_by"] == "yolo_mode"
