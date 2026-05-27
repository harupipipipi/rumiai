from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def _reset_company_store():
    from domain.agent_runtime.run_store import AgentRunStore
    from domain.company.runtime_store import CompanyRuntimeStore
    from domain.company.store import CompanyStore

    AgentRunStore._instance = None
    CompanyRuntimeStore._instance = None
    CompanyStore._instance = None


def _reset_defaultspack_singletons():
    from domain.agent.org_manager import OrgManager
    from domain.agent.scheduler import Scheduler
    from domain.chat.store import ChatStore
    from domain.company.runtime_store import CompanyRuntimeStore
    from domain.company.store import CompanyStore

    scheduler = Scheduler._instance
    if scheduler is not None:
        for schedule_id in list(getattr(scheduler, "_timers", {}).keys()):
            scheduler._cancel_timer(schedule_id)
    Scheduler._instance = None
    OrgManager._instance = None
    ChatStore._instance = None
    CompanyRuntimeStore._instance = None
    CompanyStore._instance = None


def test_company_store_crud_and_json_persistence(tmp_path, monkeypatch):
    from domain.company.store import CompanyStore

    monkeypatch.setenv("RUMI_DEFAULTSPACK_COMPANY_STORE_PATH", str(tmp_path / "companies"))
    _reset_company_store()

    store = CompanyStore()
    company = store.create_company(
        company_id="acme",
        name="Acme Company",
        description="Test company",
        metadata={"source": "test"},
    )

    assert company["id"] == "acme"
    assert company["settings"]["dispatch_policy"] == "local_queue_only"
    assert "project_manager" in company["agents"]
    assert "ops-company" in company["channels"]

    updated = store.update_company("acme", {"name": "Acme Updated", "metadata": {"tier": "p2p"}})
    assert updated["name"] == "Acme Updated"
    assert updated["metadata"]["source"] == "test"
    assert updated["metadata"]["tier"] == "p2p"

    persisted = json.loads((tmp_path / "companies" / "companies.json").read_text(encoding="utf-8"))
    assert persisted["schema_version"] == 1
    assert persisted["companies"]["acme"]["name"] == "Acme Updated"

    _reset_company_store()
    reloaded = CompanyStore().get_company("acme")
    assert reloaded["metadata"]["tier"] == "p2p"


def test_company_blocks_return_ok_error_envelopes(tmp_path, monkeypatch):
    from blocks.company import create, delete, get, list as company_list, update

    monkeypatch.setenv("RUMI_DEFAULTSPACK_COMPANY_STORE_PATH", str(tmp_path / "companies"))
    _reset_company_store()

    created = create.run({"id": "blockco", "name": "Block Co"}, {})
    listed = company_list.run({}, {})
    fetched = get.run({"company_id": "blockco"}, {})
    updated = update.run({"company_id": "blockco", "updates": {"description": "Changed"}}, {})
    missing = get.run({"company_id": "missing"}, {})
    deleted = delete.run({"company_id": "blockco"}, {})

    assert created["status"] == "ok"
    assert listed["data"]["total"] == 1
    assert fetched["data"]["id"] == "blockco"
    assert updated["data"]["description"] == "Changed"
    assert missing["status"] == "error"
    assert missing["error"]["code"] == "NOT_FOUND"
    assert deleted["data"]["deleted"] is True


def test_mentions_create_queued_tasks_and_dispatches_agent_runs(tmp_path, monkeypatch):
    from blocks.company import bootstrap, dispatch, mention, tasks

    monkeypatch.setenv("RUMI_DEFAULTSPACK_COMPANY_STORE_PATH", str(tmp_path / "companies"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_COMPANY_RUNTIME_DB_PATH", str(tmp_path / "company_runtime.db"))
    _reset_company_store()

    bootstrapped = bootstrap.run({}, {})
    company_id = bootstrapped["data"]["company"]["id"]

    def fake_dispatch(envelope, context):
        return {
            "status": "queued",
            "delegate": {"execution_id": "run_" + envelope.target["agent_id"], "status": "queued"},
            "result": {"status": "queued"},
        }

    monkeypatch.setattr("domain.company.run_dispatcher.dispatch_input", fake_dispatch)

    resolved = mention.run(
        {
            "action": "resolve",
            "company_id": company_id,
            "content": "@pm please split this, @coding_engineer implement it, @reviewer review it",
        },
        {},
    )
    assert resolved["data"]["resolved_agent_ids"] == [
        "project_manager",
        "coding_engineer",
        "reviewer",
    ]

    created = mention.run(
        {
            "company_id": company_id,
            "sender_id": "client",
            "content": "@pm hand this to @coding_engineer and have @reviewer check it",
        },
        {},
    )
    task = created["data"]["task"]
    assert task["status"] == "queued"
    assert task["source"] == "mention"
    assert task["target_agent_ids"] == ["project_manager"]
    assert created["data"]["message"]["task_ids"] == [route["task_id"] for route in created["data"]["routes"]]
    assert {route["agent_id"] for route in created["data"]["routes"]} == {"project_manager", "coding_engineer", "reviewer"}

    dispatched = dispatch.run(
        {
            "company_id": company_id,
            "task_id": task["id"],
            "requested_by": "test",
            "policy": {"direct_tool_execution": True, "mode": "execute_now"},
        },
        {},
    )
    assert dispatched["data"]["dispatch"]["status"] == "queued"
    assert dispatched["data"]["dispatch"]["policy"]["mode"] == "agent_delegate"
    assert dispatched["data"]["dispatch"]["policy"]["direct_tool_execution"] is False
    assert dispatched["data"]["run_links"]

    listed = tasks.run({"company_id": company_id, "status": "queued"}, {})
    assert listed["data"]["total"] >= 3

    all_mentions = mention.run({"action": "resolve", "company_id": company_id, "content": "@all"}, {})
    assert len(all_mentions["data"]["resolved_agent_ids"]) == 9


def test_inbound_routes_ingest_message_and_queue_task(tmp_path, monkeypatch):
    from blocks.company import bootstrap, inbound_routes, messages

    monkeypatch.setenv("RUMI_DEFAULTSPACK_COMPANY_STORE_PATH", str(tmp_path / "companies"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_COMPANY_RUNTIME_DB_PATH", str(tmp_path / "company_runtime.db"))
    _reset_company_store()

    company_id = bootstrap.run({}, {})["data"]["company"]["id"]
    route = inbound_routes.run(
        {
            "action": "upsert",
            "company_id": company_id,
            "route": {
                "id": "slack-team",
                "provider": "slack",
                "source": "C123",
                "channel_id": "ops-company",
            },
        },
        {},
    )
    ingested = inbound_routes.run(
        {
            "action": "ingest",
            "company_id": company_id,
            "route_id": "slack-team",
            "sender_id": "U123",
            "content": "@reviewer check the latest build notes",
        },
        {},
    )
    listed_messages = messages.run({"company_id": company_id, "channel_id": "ops-company"}, {})

    assert route["data"]["id"] == "slack-team"
    assert ingested["data"]["task"]["target_agent_ids"] == ["reviewer"]
    assert listed_messages["data"]["total"] == 1
    assert listed_messages["data"]["messages"][0]["metadata"]["route_id"] == "slack-team"


def test_operations_company_runtime_syncs_default_company_record(tmp_path, monkeypatch):
    from ecosystem.rumi_operations_company_pack.domain.agent.operations_company import OperationsCompanyRuntime
    from domain.agent.scheduler import Scheduler
    from domain.chat.store import ChatStore

    _reset_defaultspack_singletons()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(tmp_path / "chat" / "conversations.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_OPERATIONS_STATE_PATH", str(tmp_path / "ops" / "state.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_COMPANY_STORE_PATH", str(tmp_path / "companies"))

    status = OperationsCompanyRuntime().bootstrap(start_nonstop=True, heartbeat_minutes=30, model="stub/default")

    assert status["bootstrapped"] is True
    assert status["company"]["id"] == "operations-company"
    assert status["company"]["conversation_group_id"] == "company:operations-company"
    assert status["company"]["metadata"]["legacy_org_id"] == status["org_id"]
    assert status["company"]["metadata"]["conversation_id"] == status["conversation_id"]
    assert status["company"]["agents"]["project_manager"]["system_prompt"]
    assert "do not write production code" in status["company"]["agents"]["project_manager"]["system_prompt"]

    conversation = ChatStore().get_conversation(status["conversation_id"])
    assert conversation["group_id"] == "company:operations-company"

    persisted = json.loads((tmp_path / "companies" / "companies.json").read_text(encoding="utf-8"))
    assert persisted["companies"]["operations-company"]["metadata"]["legacy_org_id"] == status["org_id"]

    for schedule in status["schedules"]:
        Scheduler().delete_schedule(schedule["id"])
    _reset_defaultspack_singletons()


def test_mimo_coding_company_runtime_syncs_default_company_record(tmp_path, monkeypatch):
    from ecosystem.rumi_operations_company_pack.domain.agent.mimo_coding_company import MimoCodingCompanyRuntime
    from domain.agent.scheduler import Scheduler
    from domain.chat.store import ChatStore

    _reset_defaultspack_singletons()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(tmp_path / "chat" / "conversations.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_MIMO_CODING_STATE_PATH", str(tmp_path / "mimo" / "state.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_COMPANY_STORE_PATH", str(tmp_path / "companies"))

    runtime = MimoCodingCompanyRuntime(pack_root=tmp_path / "ops_pack")
    status = runtime.bootstrap(
        start_nonstop=True,
        heartbeat_minutes=30,
        review_interval_minutes=180,
        qa_interval_minutes=240,
        model="stub/default",
        vision_model="stub/default",
        fast_model="stub/default",
        seed_knowledge=False,
    )

    assert status["bootstrapped"] is True
    assert status["company"]["id"] == "mimo-coding-company"
    assert status["company"]["conversation_group_id"] == "company:mimo-coding-company"
    assert status["company"]["metadata"]["conversation_id"] == status["conversation_id"]
    assert status["company"]["metadata"]["self_improving"] is True
    assert status["company"]["metadata"]["autonomy_board"]["next_focus"][0]["id"] == "initial_harness_review"
    assert status["company"]["metadata"]["qa_swarm_plan"]["workers"][0]["mission"]
    assert len(status["company"]["metadata"]["stream_task_ids"]) == 6
    assert status["company"]["agents"]["toolsmith"]["system_prompt"]
    assert "build the smallest viable one instead of stopping" in status["company"]["agents"]["toolsmith"]["system_prompt"]

    conversation = ChatStore().get_conversation(status["conversation_id"])
    assert conversation["group_id"] == "company:mimo-coding-company"

    persisted = json.loads((tmp_path / "companies" / "companies.json").read_text(encoding="utf-8"))
    assert persisted["companies"]["mimo-coding-company"]["metadata"]["conversation_id"] == status["conversation_id"]

    for schedule in status["schedules"]:
        Scheduler().delete_schedule(schedule["id"])
    _reset_defaultspack_singletons()
