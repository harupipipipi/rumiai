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
