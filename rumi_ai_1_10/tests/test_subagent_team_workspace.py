from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


UUIDISH_ID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)


def _reset_team_workspace_singletons() -> None:
    from domain.agent_runtime.run_store import AgentRunStore
    from domain.company.runtime_store import CompanyRuntimeStore
    from domain.company.store import CompanyStore
    from domain.input import action_registry
    from domain.tool.registry import ToolRegistry
    from domain.tool.runtime_creator import RuntimeToolCreator

    AgentRunStore._instance = None
    CompanyRuntimeStore._instance = None
    CompanyStore._instance = None
    ToolRegistry._instance = None
    RuntimeToolCreator._instance = None
    action_registry._DEFAULT_REGISTRY = None


def _configure_temp_runtime(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RUMI_DEFAULTSPACK_COMPANY_STORE_PATH", str(tmp_path / "companies"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_COMPANY_RUNTIME_DB_PATH", str(tmp_path / "company_runtime.db"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_RUNTIME_DIR", str(tmp_path / "agent_runtime"))
    _reset_team_workspace_singletons()


def _create_workspace(*, settings: dict[str, Any] | None = None) -> tuple[Any, Any, dict[str, Any]]:
    from domain.company.runtime_store import CompanyRuntimeStore
    from domain.company.store import CompanyStore

    store = CompanyStore()
    runtime_store = CompanyRuntimeStore()
    company = store.create_company(
        company_id="tw_short",
        name="Subagent Team",
        settings=settings,
        metadata={"surface": "subagent_team_workspace"},
    )
    return store, runtime_store, company


def test_team_workspace_short_ids_are_stable_and_non_uuid():
    from domain.subagent_team.ids import ensure_short_id, generate_short_id, slug_id, stable_short_id
    from domain.subagent_team.normalizers import normalize_team_agent, normalize_team_channel

    first = stable_short_id("ag", "Coder Kai")
    repeated = stable_short_id("ag", "Coder Kai")
    generated = generate_short_id("ag", existing=[first], length=7)
    ensured, metadata = ensure_short_id({}, prefix="ag", seed="Coder Kai", existing=[first])

    assert first == repeated
    assert generated != first
    assert ensured != first
    assert metadata["short_id"] == ensured
    for public_id in (first, generated, ensured, slug_id("Ship Room!!!", max_length=24)):
        assert len(public_id) <= 24
        assert UUIDISH_ID_RE.search(public_id) is None
        assert "/" not in public_id and " " not in public_id

    agent = normalize_team_agent({"agent_id": "coder_kai", "display_name": "Coder Kai"})
    channel = normalize_team_channel({"id": "ship-room", "name": "Ship Room"})
    assert agent["metadata"]["short_id"].startswith("ag_")
    assert channel["metadata"]["short_id"].startswith("ch_")


def test_rich_policy_caps_active_subagents_when_rich_is_off(tmp_path, monkeypatch):
    _configure_temp_runtime(tmp_path, monkeypatch)
    _create_workspace()

    from domain.subagent_team.rich_policy import RichPolicy, evaluate_rich_payload

    payload = evaluate_rich_payload(
        {
            "content": "/rich " + ("x" * 30),
            "rich_payload": {"blocks": [{"id": "a"}, {"id": "b"}, {"id": "c"}]},
            "attachments": [{"name": "a"}, {"name": "b"}],
        },
        policy=RichPolicy(max_text_chars=12, max_blocks=2, max_attachments=1),
    )

    assert payload["requested"] is True
    assert payload["clipped"] is True
    assert payload["result"] == {"content_chars": 12, "blocks": 2, "attachments": 1}
    assert payload["original"] == {"content_chars": 36, "blocks": 3, "attachments": 2}
    assert payload["content"].endswith("...")


def test_pm_gate_blocks_large_or_risky_goals_until_pm_approval():
    from domain.subagent_team.pm_gate import gated_content, pm_gate_decision

    gate = pm_gate_decision(
        sender_id="user",
        content="@coding_engineer implement and push",
        target_agent_ids=["coding_engineer", "reviewer"],
        rich_requested=True,
    )

    assert gate["requires_pm"] is True
    assert gate["requested_target_agent_ids"] == ["coding_engineer", "reviewer"]
    assert gate["target_agent_ids"] == ["project_manager"]
    assert gate["route"] == "pm_gate"
    gated = gated_content(
        content="@coding_engineer implement and push",
        sender_id="user",
        gate=gate,
    )
    assert gated.startswith("@project_manager PM gate request")
    assert "@coding_engineer" not in gated
    assert "at coding_engineer" in gated

    pm_gate = pm_gate_decision(
        sender_id="project_manager",
        content="@coding_engineer implement",
        target_agent_ids=["coding_engineer"],
    )
    assert pm_gate["requires_pm"] is False
    assert pm_gate["target_agent_ids"] == ["coding_engineer"]


def test_creator_preview_returns_plan_without_workspace_side_effects(tmp_path, monkeypatch):
    _configure_temp_runtime(tmp_path, monkeypatch)
    store, runtime_store, company = _create_workspace()

    from domain.subagent_team.service import SubagentTeamService

    service = SubagentTeamService(company_store=store, runtime_store=runtime_store)
    before_agents = store.list_agents(company["id"]) or []
    before_channels = store.list_channels(company["id"]) or []
    before_tasks, before_task_total = runtime_store.list_tasks(company["id"], limit=200)
    before_messages, before_message_total = runtime_store.list_messages(company["id"], limit=200)

    preview = service.creator_preview(
        company["id"],
        {
            "action": "message",
            "content": "@coding_engineer implement the upload fix with /rich context",
            "sender_id": "user",
            "target_agent_ids": ["coding_engineer"],
            "rich": True,
            "approved": True,
        },
    )

    after_agents = store.list_agents(company["id"]) or []
    after_channels = store.list_channels(company["id"]) or []
    after_tasks, after_task_total = runtime_store.list_tasks(company["id"], limit=200)
    after_messages, after_message_total = runtime_store.list_messages(company["id"], limit=200)

    assert preview is not None
    assert preview["will_execute_tools"] is False
    assert preview["routing"]["direct_tool_execution"] is False
    assert preview["routing"]["target_agent_ids"] == ["project_manager"]
    assert preview["pm_gate"]["requires_pm"] is True
    assert preview["rich"]["requested"] is True
    assert preview["lifecycle"]["managed_by"] == "creator"
    assert preview["lifecycle"]["approval_bypass"] is False
    assert len(after_agents) == len(before_agents)
    assert len(after_channels) == len(before_channels)
    assert before_task_total == after_task_total
    assert before_message_total == after_message_total
    assert before_tasks == after_tasks
    assert before_messages == after_messages


def test_file_tree_payload_hides_absolute_workspace_root(tmp_path):
    workspace = tmp_path / "team-workspace"
    workspace.mkdir()
    (workspace / "notes.txt").write_text("hello\n", encoding="utf-8")

    from domain.subagent_team.file_tree import build_file_tree

    payload = build_file_tree(
        {"workspace_root": str(workspace), "directory": ".", "include_git": False},
        {},
    )
    encoded = json.dumps(payload, sort_keys=True)

    assert str(workspace.resolve()) not in encoded
    assert "/Users/" not in encoded
    assert payload["root"] == "."
    assert str(payload["workspace_root"]).startswith("workspace:")
    assert str(payload["workspace_id"]).startswith("ws_")
    assert payload["files"][0]["path"] == "notes.txt"


def test_file_tree_open_returns_sanitized_file_preview_and_channel_history(tmp_path, monkeypatch):
    _configure_temp_runtime(tmp_path, monkeypatch)
    store, runtime_store, company = _create_workspace()
    workspace = tmp_path / "team-workspace"
    workspace.mkdir()
    (workspace / "notes.txt").write_text(f"root={workspace.resolve()}\nhello\n", encoding="utf-8")

    from blocks.subagent_team import file_tree as file_tree_block

    opened_file = file_tree_block.run(
        {
            "action": "open",
            "workspace_root": str(workspace),
            "path": "notes.txt",
            "include_git": False,
        },
        {},
    )
    assert opened_file["status"] == "ok"
    assert opened_file["data"]["kind"] == "file"
    assert opened_file["data"]["path"] == "notes.txt"
    assert str(workspace.resolve()) not in json.dumps(opened_file["data"], sort_keys=True)
    assert opened_file["data"]["workspace_root"].startswith("workspace:")
    assert "hello" in opened_file["data"]["preview"]

    runtime_store.add_message(
        company["id"],
        channel_id="ops-company",
        sender_id="project_manager",
        content="history entry",
    )
    opened_history = file_tree_block.run(
        {
            "action": "open",
            "company_id": company["id"],
            "node_type": "channel",
            "node_id": "channel:ops-company",
        },
        {},
    )
    assert opened_history["status"] == "ok"
    assert opened_history["data"]["kind"] == "channel"
    assert opened_history["data"]["messages"][0]["content"] == "history entry"
    assert "/Users/" not in json.dumps(opened_history["data"], sort_keys=True)


def test_channel_check_context_includes_membership_pm_gate_and_rich_policy(tmp_path, monkeypatch):
    _configure_temp_runtime(tmp_path, monkeypatch)
    store, runtime_store, company = _create_workspace()

    from domain.subagent_team.service import SubagentTeamService

    service = SubagentTeamService(company_store=store, runtime_store=runtime_store)
    service.upsert_agent(company["id"], {"agent_id": "coding_engineer", "display_name": "Coding Engineer"})
    channel = service.upsert_channel(
        company["id"],
        {"id": "ship-room", "name": "Ship Room", "members": ["project_manager", "coding_engineer"]},
    )
    runtime_store.add_message(
        company["id"],
        channel_id="ship-room",
        sender_id="user",
        content="@coding_engineer please continue",
    )
    runtime_store.create_task(
        company["id"],
        channel_id="ship-room",
        title="Upload fix",
        description="Continue implementation",
        target_agent_ids=["coding_engineer"],
        status="queued",
    )

    context = service.channel_check(company["id"], {"channel_id": channel["id"], "limit": 10})

    assert context is not None
    assert context["kind"] == "channel.check"
    assert context["company_id"] == company["id"]
    assert context["channel"]["id"] == "ship-room"
    assert context["message_total"] == 1
    assert context["task_total"] == 1
    assert context["open_tasks"][0]["target_agent_ids"] == ["coding_engineer"]
    assert "Use PM gates for direct specialist work from non-PM senders." in context["instructions"]
    assert context["allowed"] is True
    assert context["agent_is_member"] is False
    assert context["pm_required"] is False
    assert context["rich_allowed"] is True


def test_pm_decision_requires_stored_manager_actor_and_ignores_client_approval_flags(tmp_path, monkeypatch):
    _configure_temp_runtime(tmp_path, monkeypatch)
    store, runtime_store, company = _create_workspace()

    from blocks.subagent_team import goals as goals_block

    task = runtime_store.create_task(
        company["id"],
        channel_id="ops-company",
        title="Ship guarded change",
        description="Needs approval",
        target_agent_ids=["coding_engineer"],
        source="goal",
        status="waiting_approval",
    )

    worker_approve = goals_block.run(
        {
            "company_id": company["id"],
            "action": "approve",
            "goal_id": task["task_id"],
            "actor_id": "coding_engineer",
            "approved": True,
            "_tool_server_approved": True,
            "approval_token": "client-token",
        },
        {},
    )
    assert worker_approve["status"] == "error"
    assert worker_approve["error"]["code"] == "ACTOR_REQUIRED"

    spoofed_pm = goals_block.run(
        {
            "company_id": company["id"],
            "action": "approve",
            "goal_id": task["task_id"],
            "actor_id": "project_manager",
            "approved": True,
            "approval_token": "client-token",
        },
        {"actor_id": "coding_engineer"},
    )
    assert spoofed_pm["status"] == "error"
    assert spoofed_pm["error"]["code"] == "FORBIDDEN"

    worker_complete = goals_block.run(
        {
            "company_id": company["id"],
            "action": "task_complete",
            "task_id": task["task_id"],
            "actor_id": "reviewer",
            "approved": True,
        },
        {"actor_id": "reviewer"},
    )
    assert worker_complete["status"] == "error"
    assert worker_complete["error"]["code"] == "FORBIDDEN"

    pm_approve = goals_block.run(
        {
            "company_id": company["id"],
            "action": "approve",
            "goal_id": task["task_id"],
            "actor_id": "project_manager",
        },
        {"actor_id": "project_manager"},
    )
    assert pm_approve["status"] == "ok"
    approved_task = pm_approve["data"]
    metadata = approved_task["metadata"]
    assert approved_task["status"] == "queued"
    assert metadata["approval"] == "approved"
    assert metadata["approval_receipt_id"].startswith("pmr_")
    assert metadata["approval_receipt"]["actor_id"] == "project_manager"
    assert metadata["approval_receipt"]["grants_user_approval"] is False


def test_rich_state_persists_and_creator_cannot_self_enable_or_exceed_cap(tmp_path, monkeypatch):
    _configure_temp_runtime(tmp_path, monkeypatch)
    store, runtime_store, company = _create_workspace()

    from blocks.subagent_team import rich as rich_block
    from domain.subagent_team.service import SubagentTeamService

    service = SubagentTeamService(company_store=store, runtime_store=runtime_store)
    status = service.rich_status(company["id"])
    assert status["rich_enabled"] is False

    blocked = service.creator_request(
        company["id"],
        {"action": "create_team", "team_size": 6, "channel_name": "Six Pack"},
    )
    assert blocked["denied"] is True
    assert blocked["code"] == "RICH_MODE_REQUIRED"

    creator_enable = rich_block.run(
        {"company_id": company["id"], "action": "set", "enabled": True, "actor_id": "creator"},
        {"actor_id": "creator"},
    )
    assert creator_enable["status"] == "error"
    assert creator_enable["error"]["code"] == "FORBIDDEN"

    spoofed_rich_enable = rich_block.run(
        {"company_id": company["id"], "action": "set", "enabled": True, "actor_id": "project_manager"},
        {"actor_id": "coding_engineer"},
    )
    assert spoofed_rich_enable["status"] == "error"
    assert spoofed_rich_enable["error"]["code"] == "FORBIDDEN"

    pm_enable = rich_block.run(
        {"company_id": company["id"], "action": "set", "enabled": True, "actor_id": "project_manager"},
        {"actor_id": "project_manager"},
    )
    assert pm_enable["status"] == "ok"
    assert pm_enable["data"]["rich_enabled"] is True

    allowed = service.creator_request(
        company["id"],
        {"action": "create_team", "team_size": 6, "channel_name": "Six Pack"},
    )
    assert allowed["allowed"] is True
    assert allowed["rich_policy"]["enabled"] is True
    assert allowed["team_size"] == 6
    assert allowed["channel"]["metadata"]["subagent_team"]["pm_agent_id"]
    for agent in allowed["agents"]:
        assert UUIDISH_ID_RE.fullmatch(agent["agent_id"])
        metadata = agent["metadata"]
        nested = metadata["subagent_team"]
        assert nested["uuid"] == agent["agent_id"]
        assert nested["short_id"] in agent["aliases"]
        assert UUIDISH_ID_RE.search(nested["short_id"]) is None

    persisted = rich_block.run({"company_id": company["id"], "action": "get"}, {})
    assert persisted["status"] == "ok"
    assert persisted["data"]["rich_enabled"] is True


def test_agents_post_uses_creator_and_keeps_legacy_slug_as_alias(tmp_path, monkeypatch):
    _configure_temp_runtime(tmp_path, monkeypatch)
    _, _, company = _create_workspace()

    from blocks.subagent_team import agents as agents_block

    created = agents_block.run(
        {
            "company_id": company["id"],
            "action": "create",
            "agent": {
                "agent_id": "legacy_coder_slug",
                "display_name": "Legacy Coder",
                "role": "coder",
            },
        },
        {},
    )

    assert created["status"] == "ok"
    payload = created["data"]
    assert payload["status"] == "created"
    agent = payload["agents"][0]
    assert UUIDISH_ID_RE.fullmatch(agent["agent_id"])
    assert "legacy_coder_slug" in agent["aliases"]
    assert agent["metadata"]["subagent_team"]["legacy_alias"] == "legacy_coder_slug"


def test_channel_check_enforced_before_message_goal_and_dm_routing(tmp_path, monkeypatch):
    _configure_temp_runtime(tmp_path, monkeypatch)
    store, runtime_store, company = _create_workspace()

    from domain.subagent_team.service import SubagentTeamService

    service = SubagentTeamService(company_store=store, runtime_store=runtime_store)
    channel = service.upsert_channel(
        company["id"],
        {"id": "pm-only", "name": "PM Only", "members": ["project_manager"]},
    )
    assert channel["id"] == "pm-only"

    message = service.send_message(
        company["id"],
        {
            "channel_id": "pm-only",
            "sender_id": "user",
            "content": "@coding_engineer please implement",
            "target_agent_ids": ["coding_engineer"],
        },
    )
    assert message["denied"] is True
    assert message["code"] == "TARGET_NOT_CHANNEL_MEMBER"

    goal = service.create_goal(
        company["id"],
        {
            "channel_id": "pm-only",
            "sender_id": "user",
            "title": "Implement safely",
            "description": "Please implement",
            "target_agent_ids": ["coding_engineer"],
        },
    )
    assert goal["denied"] is True
    assert goal["code"] == "TARGET_NOT_CHANNEL_MEMBER"

    creator_goal = service.creator_request(
        company["id"],
        {
            "action": "goal",
            "channel_id": "pm-only",
            "sender_id": "user",
            "title": "Implement through creator",
            "description": "Please implement",
            "target_agent_ids": ["coding_engineer"],
        },
    )
    assert creator_goal["denied"] is True
    assert creator_goal["code"] == "TARGET_NOT_CHANNEL_MEMBER"

    dm = service.send_dm(
        company["id"],
        {
            "sender_id": "user",
            "agent_id": "not_a_real_agent",
            "content": "hello",
        },
    )
    assert dm["denied"] is True
    assert dm["code"] == "TARGET_NOT_FOUND"


def test_channels_with_five_members_require_pm_unless_creator_supplies_one(tmp_path, monkeypatch):
    _configure_temp_runtime(tmp_path, monkeypatch)
    store, runtime_store, company = _create_workspace()

    from domain.subagent_team.service import SubagentTeamService

    service = SubagentTeamService(company_store=store, runtime_store=runtime_store)
    no_pm = service.upsert_channel(
        company["id"],
        {
            "id": "large-no-pm",
            "name": "Large No PM",
            "members": ["coding_engineer", "reviewer", "research_specialist", "scribe", "scheduler"],
        },
    )
    assert no_pm["denied"] is True
    assert no_pm["code"] == "PM_REQUIRED"

    with_pm = service.upsert_channel(
        company["id"],
        {
            "id": "large-with-pm",
            "name": "Large With PM",
            "members": ["project_manager", "coding_engineer", "reviewer", "research_specialist", "scribe"],
        },
    )
    assert with_pm["id"] == "large-with-pm"
    assert with_pm["metadata"]["subagent_team"]["pm_required"] is True

    store.update_settings(company["id"], {"subagent_team": {"rich_enabled": True}})
    creator = service.creator_request(
        company["id"],
        {"action": "create_team", "team_size": 5, "channel_name": "Creator Large"},
    )
    assert creator["allowed"] is True
    assert creator["channel"]["metadata"]["subagent_team"]["pm_agent_id"]


def test_subagent_team_company_write_bypass_is_blocked_on_company_routes(tmp_path, monkeypatch):
    _configure_temp_runtime(tmp_path, monkeypatch)
    _, _, company = _create_workspace()

    from blocks.company import create as company_create
    from blocks.company import channels as company_channels
    from blocks.company import messages as company_messages
    from blocks.company import settings as company_settings
    from blocks.company import tasks as company_tasks
    from blocks.company import bootstrap as company_bootstrap
    from blocks.company import status as company_status

    channel_write = company_channels.run(
        {"company_id": company["id"], "action": "create", "channel": {"id": "bypass", "members": []}},
        {},
    )
    assert channel_write["status"] == "error"
    assert channel_write["error"]["code"] == "SUBAGENT_TEAM_POLICY_REQUIRED"

    message_write = company_messages.run(
        {"company_id": company["id"], "action": "create", "channel_id": "ops-company", "content": "@coding_engineer bypass"},
        {},
    )
    assert message_write["status"] == "error"
    assert message_write["error"]["code"] == "SUBAGENT_TEAM_POLICY_REQUIRED"

    task_write = company_tasks.run(
        {"company_id": company["id"], "action": "create", "title": "bypass", "target_agent_ids": ["coding_engineer"]},
        {},
    )
    assert task_write["status"] == "error"
    assert task_write["error"]["code"] == "SUBAGENT_TEAM_POLICY_REQUIRED"

    settings_write = company_settings.run(
        {"company_id": company["id"], "action": "update", "settings": {"subagent_team": {"rich_enabled": True}}},
        {},
    )
    assert settings_write["status"] == "error"
    assert settings_write["error"]["code"] == "SUBAGENT_TEAM_POLICY_REQUIRED"

    ui_bootstrap = company_status.run({"conversation_id": "chat-main-guard", "bootstrap": True}, {})
    assert ui_bootstrap["status"] == "ok"
    ui_company_id = ui_bootstrap["data"]["company_id"]
    assert ui_bootstrap["data"]["company"]["metadata"]["surface"] == "main_chat"
    ui_message_write = company_messages.run(
        {"company_id": ui_company_id, "action": "create", "channel_id": "ops-company", "content": "@coding_engineer bypass"},
        {},
    )
    assert ui_message_write["status"] == "ok"
    ui_task_write = company_tasks.run(
        {"company_id": ui_company_id, "action": "create", "title": "normal task", "target_agent_ids": ["coding_engineer"]},
        {},
    )
    assert ui_task_write["status"] == "ok"

    marker_bootstrap = company_bootstrap.run(
        {
            "conversation_id": "subagent-chat-guard",
            "scope": "conversation",
            "metadata": {
                "conversation_id": "subagent-chat-guard",
                "surface": "subagent_team_workspace",
                "subagent_team": True,
            },
        },
        {},
    )
    assert marker_bootstrap["status"] == "ok"
    marker_company_id = marker_bootstrap["data"]["company"]["id"]
    marker_message_write = company_messages.run(
        {"company_id": marker_company_id, "action": "create", "channel_id": "ops-company", "content": "@coding_engineer bypass"},
        {},
    )
    assert marker_message_write["status"] == "error"
    assert marker_message_write["error"]["code"] == "SUBAGENT_TEAM_POLICY_REQUIRED"
    marker_task_write = company_tasks.run(
        {"company_id": marker_company_id, "action": "create", "title": "blocked task", "target_agent_ids": ["coding_engineer"]},
        {},
    )
    assert marker_task_write["status"] == "error"
    assert marker_task_write["error"]["code"] == "SUBAGENT_TEAM_POLICY_REQUIRED"

    normal = company_create.run({"id": "plain-company", "name": "Plain Company"}, {})
    assert normal["status"] == "ok"
    normal_message = company_messages.run(
        {"company_id": "plain-company", "action": "create", "channel_id": "ops-company", "content": "hello"},
        {},
    )
    assert normal_message["status"] == "ok"


def test_subagent_team_routes_are_registered_in_runtime_and_api_map():
    from ecosystem.defaultspack.transport.registry import canonical_http_route_specs

    expected_routes = {
        ("GET", "/api/subagent-team/status"),
        ("GET", "/api/subagent-team/channels"),
        ("POST", "/api/subagent-team/channels"),
        ("POST", "/api/subagent-team/channels/{channel_id}/messages"),
        ("POST", "/api/subagent-team/creator/test"),
        ("GET", "/api/subagent-team/creator/settings"),
        ("PATCH", "/api/subagent-team/creator/settings"),
        ("GET", "/api/subagent-team/rich"),
        ("POST", "/api/subagent-team/rich"),
        ("POST", "/api/subagent-team/channel-check"),
        ("POST", "/api/subagent-team/goals"),
        ("POST", "/api/subagent-team/goals/{goal_id}/approve"),
        ("POST", "/api/subagent-team/tasks/{task_id}/complete"),
    }

    runtime_routes = {(spec.method, spec.pattern) for spec in canonical_http_route_specs()}
    assert expected_routes <= runtime_routes

    routes_json = json.loads((DEFAULTSPACK_ROOT / "routes.json").read_text(encoding="utf-8"))
    api_map_routes = {
        (str(route.get("method") or "").upper(), str(route.get("path") or ""))
        for route in routes_json.get("routes", [])
        if isinstance(route, dict)
    }
    assert expected_routes <= api_map_routes


def test_subagent_team_http_route_defaults_execute_blocks(tmp_path, monkeypatch):
    _configure_temp_runtime(tmp_path, monkeypatch)
    _, _, company = _create_workspace()

    from ecosystem.defaultspack.transport.registry import canonical_http_route_specs

    specs = {(spec.method, spec.pattern): spec for spec in canonical_http_route_specs()}
    rich_spec = specs[("POST", "/api/subagent-team/rich")]
    assert rich_spec.defaults["action"] == "set"

    from blocks.subagent_team import rich as rich_block

    result = rich_block.run(
        {
            **rich_spec.defaults,
            "company_id": company["id"],
            "actor_id": "project_manager",
            "enabled": True,
        },
        {"actor_id": "project_manager"},
    )

    assert result["status"] == "ok"
    assert result["data"]["rich_enabled"] is True
