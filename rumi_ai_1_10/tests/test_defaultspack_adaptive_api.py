from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(DEFAULTSPACK_ROOT) not in sys.path:
    sys.path.insert(0, str(DEFAULTSPACK_ROOT))

pytestmark = pytest.mark.contract


def test_adaptive_dispatch_compile_apply_and_activity(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUMI_USER_DATA", str(tmp_path))
    from domain.adaptive.service import AdaptiveRuntimeService, dispatch

    compiled = dispatch(
        "onboarding_compile",
        {"profile_id": "coding", "answers": {"profile_id": "coding", "preset_id": "maximum_local_autonomy"}},
        {},
    )
    assert compiled["status"] == "ok"
    plan = compiled["data"]["plan"]

    applied = dispatch("onboarding_apply", {"profile_id": "coding", "plan": plan}, {})
    assert applied["status"] == "ok"
    assert applied["data"]["applied"] is True

    frozen = dispatch("freeze_set", {"profile_id": "coding", "frozen": True, "reason": "test"}, {})
    assert frozen["status"] == "ok"
    snapshot = AdaptiveRuntimeService(profile_id="coding").activity_snapshot()
    assert snapshot["freeze"]["frozen"] is True
    assert snapshot["events"]
    blocked = dispatch("lease_acquire", {"profile_id": "coding", "resource": "src/App.tsx"}, {})
    assert blocked["status"] == "error"
    assert blocked["code"] == "ADAPTIVE_FROZEN"


def test_adaptive_apply_requires_plan_and_undo_restores_active_profile(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUMI_USER_DATA", str(tmp_path))
    from core_runtime.operating_profile import OperatingProfilePlanStore
    from domain.adaptive.service import dispatch

    missing = dispatch(
        "onboarding_apply",
        {"profile_id": "coding", "answers": {"profile_id": "coding", "preset": "max_local_autonomy"}},
        {},
    )
    assert missing["status"] == "error"
    assert missing["code"] == "INVALID_INPUT"

    initial = dispatch(
        "onboarding_compile",
        {"profile_id": "coding", "answers": {"profile_id": "coding", "preset": "discussion_only"}},
        {},
    )
    assert initial["status"] == "ok"
    assert dispatch("onboarding_apply", {"profile_id": "coding", "plan": initial["data"]["plan"]}, {})["status"] == "ok"

    target = dispatch(
        "onboarding_compile",
        {"profile_id": "coding", "answers": {"profile_id": "coding", "preset": "max_local_autonomy"}},
        {},
    )
    assert target["status"] == "ok"
    assert dispatch("onboarding_apply", {"profile_id": "coding", "plan": target["data"]["plan"]}, {})["status"] == "ok"

    undone = dispatch("onboarding_undo", {"profile_id": "coding"}, {})
    assert undone["status"] == "ok"
    restored = OperatingProfilePlanStore().load_active_profile("coding")
    assert restored is not None
    assert restored.preset_id == "discussion_only"


def test_adaptive_freeze_blocks_real_tool_and_public_function_dispatch(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUMI_USER_DATA", str(tmp_path))
    from domain.adaptive.service import dispatch
    from domain.function_runtime.dispatcher import run_defaultspack_function
    from domain.tool.executor import ToolExecutor

    frozen = dispatch("freeze_set", {"profile_id": "coding", "frozen": True, "reason": "incident"}, {})
    assert frozen["status"] == "ok"

    class Registry:
        def get(self, name):
            return {
                "tool_id": name,
                "name": name,
                "execution": {"type": "local"},
                "metadata": {"category": "external_message"},
            }

    def must_not_run(*args, **kwargs):  # pragma: no cover - proves the guard is preflight
        raise AssertionError("tool execution should be blocked before local execution")

    executor = ToolExecutor()
    executor._registry = Registry()
    monkeypatch.setattr(executor, "_execute_local", must_not_run)
    tool_result = executor.execute(
        "external_send",
        {"payload": {"text": "hello"}},
        {"profile_id": "coding", "_tool_server_approved": True, "profile_policy": {"yolo_mode": True}},
    )

    assert tool_result["is_error"] is True
    assert tool_result["adaptive_policy"]["code"] == "ADAPTIVE_FROZEN"

    browser_result = run_defaultspack_function(
        "browser_open_url",
        {"url": "https://example.invalid", "approved": True},
        {"profile_id": "coding", "_tool_server_approved": True},
    )
    assert browser_result["status"] == "ok"
    assert browser_result["data"]["adaptive_policy"]["code"] == "ADAPTIVE_FROZEN"

    terminal_result = run_defaultspack_function(
        "coding_terminal_exec",
        {"command": "echo should-not-run", "approved": True},
        {"profile_id": "coding", "_tool_server_approved": True},
    )
    assert terminal_result["status"] == "error"
    assert terminal_result["error"]["code"] == "ADAPTIVE_FROZEN"


def test_active_operating_profile_denies_tool_and_public_function_dispatch(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUMI_USER_DATA", str(tmp_path))
    from core_runtime.operating_profile import OperatingProfilePlanStore, compile_operating_profile
    from domain.function_runtime.dispatcher import run_defaultspack_function
    from domain.tool.executor import ToolExecutor

    store = OperatingProfilePlanStore()
    profile = compile_operating_profile({"profile_id": "coding", "preset": "discussion_only"})
    store.apply_plan(store.create_plan("coding", profile, reason="test deny"))

    class Registry:
        def get(self, name):
            return {
                "tool_id": name,
                "name": name,
                "execution": {"type": "local"},
                "metadata": {"category": "shell"},
            }

    def must_not_run(*args, **kwargs):  # pragma: no cover - proves the guard is preflight
        raise AssertionError("tool execution should be blocked by active operating profile")

    executor = ToolExecutor()
    executor._registry = Registry()
    monkeypatch.setattr(executor, "_execute_local", must_not_run)
    tool_result = executor.execute(
        "coding_terminal_exec",
        {"command": "echo denied"},
        {"profile_id": "coding", "_tool_server_approved": True},
    )
    assert tool_result["is_error"] is True
    assert tool_result["adaptive_policy"]["code"] == "ADAPTIVE_PROFILE_DENIED"

    function_result = run_defaultspack_function(
        "coding_terminal_exec",
        {"command": "echo denied", "approved": True},
        {"profile_id": "coding", "_tool_server_approved": True},
    )
    assert function_result["status"] == "error"
    assert function_result["error"]["code"] == "ADAPTIVE_PROFILE_DENIED"


def test_adaptive_guard_splits_git_commit_push_and_merge_actions() -> None:
    from domain.adaptive.guard import action_for_function, action_for_tool

    assert action_for_function("coding_git_commit") == "git_commit"
    assert action_for_function("coding_git_push") == "git_push"
    assert action_for_function("coding_git_merge") == "git_merge"
    assert action_for_tool("git_commit", {}, {}) == "git_commit"
    assert action_for_tool("git_push", {}, {}) == "git_push"
    assert action_for_tool("git_merge", {}, {}) == "git_merge"


def test_adaptive_generated_functions_register_into_shared_registry() -> None:
    from core_runtime.function_registry import FunctionRegistry
    from domain.function_runtime.bridge import ensure_defaultspack_functions_registered

    registry = FunctionRegistry()

    class Container:
        def get_or_none(self, name: str):
            if name == "function_registry":
                return registry
            return None

    registered = ensure_defaultspack_functions_registered(Container())
    entry = registry.get("defaultspack:adaptive_onboarding_status")

    assert registered > 0
    assert entry is not None
    assert entry.entrypoint == "main.py:run"
    assert entry.function_dir.name == "adaptive_onboarding_status"
    assert entry.manifest["extensions"]["defaultspack"]["block_module"] == "blocks.adaptive"


def test_context_file_read_search_and_evidence_are_bounded(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUMI_USER_DATA", str(tmp_path / "user_data"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CODING_WORKSPACE_STORE_PATH", str(tmp_path / "workspaces.json"))
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "app.py").write_text("alpha\nbeta target\ngamma target\n", encoding="utf-8")
    (workspace / "long.txt").write_text(
        "".join(f"prefix-{index:03d}-{'x' * 80}\n" for index in range(1, 40)),
        encoding="utf-8",
    )
    (workspace / ".env").write_text("TOKEN=secret\n", encoding="utf-8")

    from domain.coding.workspace_store import WorkspaceStore
    from domain.adaptive.service import dispatch

    WorkspaceStore().create(workspace, workspace_id="ws1", trusted=True)

    read = dispatch(
        "context_file_read",
        {"workspace_id": "ws1", "path": "app.py", "start_line": 2, "max_lines": 1},
        {},
    )
    assert read["status"] == "ok"
    assert read["data"]["line_count"] == 1
    assert read["data"]["lines"][0]["line"] == 2

    rear_read = dispatch(
        "context_file_read",
        {"workspace_id": "ws1", "path": "long.txt", "start_line": 20, "max_lines": 1, "max_bytes": 120},
        {},
    )
    assert rear_read["status"] == "ok"
    assert rear_read["data"]["line_count"] == 1
    assert rear_read["data"]["lines"][0]["line"] == 20
    assert rear_read["data"]["lines"][0]["text"].startswith("prefix-020-")

    search = dispatch("context_code_search", {"workspace_id": "ws1", "query": "target", "max_matches": 1}, {})
    assert search["status"] == "ok"
    assert search["data"]["count"] == 1
    assert search["data"]["truncated"] is True

    evidence = dispatch(
        "context_evidence",
        {"workspace_id": "ws1", "items": [{"path": "app.py", "start_line": 1, "max_lines": 2}]},
        {},
    )
    assert evidence["status"] == "ok"
    assert evidence["data"]["bundle_id"].startswith("ev_")

    untrusted_root = dispatch("context_file_read", {"root": str(tmp_path), "path": "repo/app.py"}, {})
    assert untrusted_root["status"] == "error"
    assert untrusted_root["code"] == "WORKSPACE_UNTRUSTED"

    absolute_path = dispatch("context_file_read", {"workspace_id": "ws1", "path": str(workspace / "app.py")}, {})
    assert absolute_path["status"] == "error"
    assert absolute_path["code"] == "PATH_OUTSIDE_WORKSPACE"

    secret_path = dispatch("context_file_read", {"workspace_id": "ws1", "path": ".env"}, {})
    assert secret_path["status"] == "error"
    assert secret_path["code"] == "PATH_RESTRICTED"


def test_prepared_actions_redact_secret_and_lease_roundtrip(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUMI_USER_DATA", str(tmp_path))
    from domain.adaptive.service import dispatch

    prepared = dispatch(
        "prepared_action_prepare",
        {"profile_id": "coding", "operation": "webhook.create", "arguments": {"shared_secret": "raw"}},
        {},
    )
    assert prepared["status"] == "ok"
    action = prepared["data"]["prepared_action"]
    assert action["display_args"]["shared_secret"] == "[REDACTED]"

    lease = dispatch("lease_acquire", {"profile_id": "coding", "resource": "src/App.tsx", "owner": "agent"}, {})
    assert lease["status"] == "ok"
    released = dispatch("lease_release", {"profile_id": "coding", "id": lease["data"]["lease"]["id"]}, {})
    assert released["status"] == "ok"
    assert released["data"]["lease"]["status"] == "released"


def test_adaptive_pack_skill_automation_and_event_state_are_not_placeholders(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUMI_USER_DATA", str(tmp_path))
    from domain.adaptive.service import dispatch
    from domain.adaptive.storage import AdaptiveStore

    recommendations = dispatch(
        "pack_recommendations_list",
        {
            "profile_id": "coding",
            "answers": {
                "profile_id": "coding",
                "use_cases": {"coding": True, "automation": True},
                "actions": {"terminal": "ask", "browser_control": "ask"},
            },
        },
        {},
    )
    assert recommendations["status"] == "ok"
    assert "degraded" not in recommendations["data"]
    assert {item["pack_id"] for item in recommendations["data"]["recommendations"]} >= {"coding", "context", "tool"}

    prepared = dispatch(
        "prepared_action_prepare",
        {
            "profile_id": "coding",
            "action_type": "automation.update",
            "arguments": {"automationId": "automation_daily_context", "patch": {"enabled": True}},
        },
        {},
    )
    assert prepared["status"] == "ok"
    action_id = prepared["data"]["prepared_action"]["action_id"]
    committed = dispatch("prepared_action_commit", {"profile_id": "coding", "action_id": action_id}, {})
    assert committed["status"] == "ok"
    assert committed["data"]["executed"] is True
    assert committed["data"]["execution_result"]["enabled"] is True
    activity = dispatch("activity_snapshot", {"profile_id": "coding"}, {})
    assert activity["status"] == "ok"
    automation = next(item for item in activity["data"]["automations"] if item["id"] == "automation_daily_context")
    assert automation["enabled"] is True

    store = AdaptiveStore("coding")
    store.write_json(
        "skills/candidates.json",
        {
            "version": 1,
            "candidates": [
                {
                    "candidate_id": "cand_success_pair",
                    "title": "Retry stable install after cache repair",
                    "evidence": {"failure_event_id": "fail1", "success_event_id": "success1"},
                }
            ],
        },
    )
    promoted = dispatch("skill_candidate_promote", {"profile_id": "coding", "candidate_id": "cand_success_pair"}, {})
    assert promoted["status"] == "ok"
    assert promoted["data"]["promoted"] is True
    assert promoted["data"]["skill"]["status"] == "active"
    rolled_back = dispatch("skill_candidate_rollback", {"profile_id": "coding", "candidate_id": "cand_success_pair"}, {})
    assert rolled_back["status"] == "ok"
    assert rolled_back["data"]["rolled_back"] is True
    assert rolled_back["data"]["skill"]["status"] == "rolled_back"

    event = dispatch(
        "event_append",
        {"profile_id": "coding", "event_type": "adaptive.test", "idempotency_key": "idem-1", "payload": {"ok": True}},
        {},
    )
    duplicate = dispatch(
        "event_append",
        {"profile_id": "coding", "event_type": "adaptive.test", "idempotency_key": "idem-1", "payload": {"ok": True}},
        {},
    )
    assert event["status"] == "ok"
    assert duplicate["status"] == "ok"
    assert duplicate["data"]["duplicate"] is True
    assert duplicate["data"]["event"]["event_id"] == event["data"]["event"]["event_id"]
    replay = dispatch("event_replay", {"profile_id": "coding", "limit": 10}, {})
    assert replay["status"] == "ok"
    assert replay["data"]["next_cursor"]


def test_adaptive_public_route_uses_function_id_operation_not_client_operation(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUMI_USER_DATA", str(tmp_path))
    from domain.function_runtime.dispatcher import run_defaultspack_function

    prepared = run_defaultspack_function(
        "adaptive_prepared_action_prepare",
        {
            "operation": "automation.update",
            "arguments": {"automationId": "automation_daily_context", "patch": {"enabled": True}},
        },
        {},
    )
    assert prepared["status"] == "ok"
    assert prepared["data"]["prepared_action"]["operation"] == "automation.update"
