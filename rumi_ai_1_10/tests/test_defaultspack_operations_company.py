from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def _reset_defaultspack_singletons():
    from domain.agent.org_manager import OrgManager
    from domain.agent.scheduler import Scheduler
    from domain.chat.store import ChatStore
    from domain.company.runtime_store import CompanyRuntimeStore
    from domain.tool.registry import ToolRegistry

    scheduler = Scheduler._instance
    if scheduler is not None:
        for schedule_id in list(getattr(scheduler, "_timers", {}).keys()):
            scheduler._cancel_timer(schedule_id)
    Scheduler._instance = None
    OrgManager._instance = None
    ChatStore._instance = None
    CompanyRuntimeStore._instance = None
    ToolRegistry._instance = None


def test_operations_company_profile_coexists_with_default_profile():
    from domain.capability.catalog import CapabilityCatalog

    manifest = CapabilityCatalog(DEFAULTSPACK_ROOT).manifest()
    profile_ids = {profile["profile_id"] for profile in manifest["profiles"]}

    assert "defaultspack.local_agent" in profile_ids
    assert "defaultspack.operations_company" in profile_ids
    assert "defaultspack.mimo_coding_company" in profile_ids
    assert manifest["counts"]["profiles"] >= 2


def test_operations_company_bootstrap_creates_org_conversation_and_heartbeat(tmp_path, monkeypatch):
    from ecosystem.rumi_operations_company_pack.domain.agent.operations_company import OperationsCompanyRuntime
    from domain.agent.scheduler import Scheduler
    from domain.chat.store import ChatStore

    _reset_defaultspack_singletons()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(tmp_path / "chat" / "conversations.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_OPERATIONS_STATE_PATH", str(tmp_path / "ops" / "state.json"))

    status = OperationsCompanyRuntime().bootstrap(start_nonstop=True, heartbeat_minutes=30, model="stub/default")

    assert status["bootstrapped"] is True
    assert status["org"]["member_count"] == 9
    assert status["conversation_id"]
    conversation = ChatStore().get_conversation(status["conversation_id"])
    assert conversation["conversation_kind"] == "operations_company"
    assert conversation["agent_id"] == "client_manager"
    assert conversation["metadata"]["profile_id"] == "defaultspack.operations_company"

    heartbeat = status["schedules"][0]
    assert heartbeat["task"]["profile_id"] == "defaultspack.operations_company"
    assert heartbeat["task"]["agent_id"] == "operations_monitor"
    assert heartbeat["task"]["conversation_id"] == status["conversation_id"]
    assert "rumi_api" in heartbeat["task"]["tool_policy"]["tool_allowlist"]

    Scheduler().delete_schedule(heartbeat["id"])
    _reset_defaultspack_singletons()


def test_operations_conversation_resolves_pack_system_prompt():
    from blocks.chat.send import _conversation_system_prompt
    from domain.prompt.manager import get_manager

    prompt = _conversation_system_prompt({"system_prompt_id": "operations_company"}, get_manager())

    assert "Rumi Operations Company" in prompt
    assert "Client Manager" in prompt


def test_mimo_coding_company_bootstrap_creates_company_conversation_and_loops(tmp_path, monkeypatch):
    from ecosystem.rumi_operations_company_pack.domain.agent.mimo_coding_company import MimoCodingCompanyRuntime
    from domain.agent.scheduler import Scheduler
    from domain.chat.store import ChatStore
    from domain.company.task_store import CompanyTaskStore

    _reset_defaultspack_singletons()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(tmp_path / "chat" / "conversations.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_COMPANY_STORE_PATH", str(tmp_path / "companies"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_MIMO_CODING_STATE_PATH", str(tmp_path / "mimo" / "state.json"))

    runtime = MimoCodingCompanyRuntime(pack_root=tmp_path / "ops_pack")
    status = runtime.bootstrap(
        start_nonstop=True,
        heartbeat_minutes=30,
        review_interval_minutes=180,
        qa_interval_minutes=240,
        model="stub/default",
        vision_model="stub/default",
        fast_model="stub/default",
        qa_targets=["http://127.0.0.1:3000"],
        docker_worker_count=4,
        docker_personas=["first_time_user", "power_user"],
        seed_knowledge=False,
        run_initial_review_now=False,
    )

    assert status["bootstrapped"] is True
    assert status["company"]["id"] == "mimo-coding-company"
    assert status["conversation_id"]
    assert status["harness"]["qa_targets"] == ["http://127.0.0.1:3000"]
    assert len(status["harness"]["seeded_task_ids"]) == 6
    assert status["harness"]["docker_swarm"]["worker_count"] == 4
    assert status["harness"]["docker_swarm"]["personas"] == ["first_time_user", "power_user"]
    assert len(status["harness"]["docker_swarm"]["workers"]) == 4
    assert status["harness"]["open_task_count"] == 6
    assert len(status["harness"]["stream_task_ids"]) == 6
    assert status["harness"]["autonomy_board"]["next_focus"][0]["id"] == "initial_harness_review"
    assert status["harness"]["qa_swarm_plan"]["workers"][0]["persona_id"] == "first_time_user"
    assert status["harness"]["qa_swarm_plan"]["workers"][0]["qa_target"] == "http://127.0.0.1:3000"
    assert Path(status["harness"]["docker_swarm"]["compose_path"]).is_file()
    assert Path(status["harness"]["docker_swarm"]["template_compose_path"]).is_file()
    assert Path(status["harness"]["docker_swarm"]["status_dir"]).is_dir()
    assert Path(status["harness"]["docker_swarm"]["supervisor_path"]).is_file()
    assert Path(status["harness"]["docker_swarm"]["workers"][0]["assignment_path"]).is_file()
    assert status["harness"]["docker_swarm"]["monitoring"]["reported_workers"] == 0
    assert "--project-name " + status["harness"]["docker_swarm"]["project_name"] in status["harness"]["docker_swarm"]["commands"]["up"]
    assert "docker ps --filter" in status["harness"]["docker_swarm"]["commands"]["docker_ps"]
    assert status["harness"]["docker_swarm"]["workers"][0]["container_name"].startswith(
        status["harness"]["docker_swarm"]["project_name"] + "-"
    )
    queued_tasks = CompanyTaskStore().list("mimo-coding-company", status="queued", limit=50, offset=0)
    assert queued_tasks is not None and queued_tasks[1] == 6
    assignment = json.loads(Path(status["harness"]["docker_swarm"]["workers"][0]["assignment_path"]).read_text(encoding="utf-8"))
    supervisor = json.loads(Path(status["harness"]["docker_swarm"]["supervisor_path"]).read_text(encoding="utf-8"))
    assert assignment["container_name"] == status["harness"]["docker_swarm"]["workers"][0]["container_name"]
    assert assignment["persona_id"] == "first_time_user"
    assert assignment["qa_target"] == "http://127.0.0.1:3000"
    assert supervisor["project_name"] == status["harness"]["docker_swarm"]["project_name"]
    assert supervisor["monitoring"]["reported_workers"] == 0
    assert supervisor["commands"]["docker_ps"] == status["harness"]["docker_swarm"]["commands"]["docker_ps"]

    conversation = ChatStore().get_conversation(status["conversation_id"])
    assert conversation["conversation_kind"] == "mimo_coding_company"
    assert conversation["agent_id"] == "client_manager"
    assert conversation["metadata"]["profile_id"] == "defaultspack.mimo_coding_company"
    assert "mimo-coding-company" in conversation["tags"]

    loop_keys = {schedule["task"]["metadata"]["loop_key"] for schedule in status["schedules"]}
    assert {"kickoff_review", "heartbeat", "improvement_loop", "qa_loop"} <= loop_keys
    assert any(schedule["task"]["agent_id"] == "browser_qa" for schedule in status["schedules"])
    heartbeat_schedule = next(schedule for schedule in status["schedules"] if schedule["task"]["metadata"]["loop_key"] == "heartbeat")
    qa_schedule = next(schedule for schedule in status["schedules"] if schedule["task"]["metadata"]["loop_key"] == "qa_loop")
    assert "0/4 workers reported status" in heartbeat_schedule["task"]["message"]
    assert "0/4 workers reported status" in qa_schedule["task"]["message"]

    for schedule in status["schedules"]:
        Scheduler().delete_schedule(schedule["id"])
    _reset_defaultspack_singletons()


def test_mimo_coding_company_bootstrap_allows_non_docker_and_unlimited_tool_calls(tmp_path, monkeypatch):
    from ecosystem.rumi_operations_company_pack.domain.agent.mimo_coding_company import MimoCodingCompanyRuntime
    from domain.agent.scheduler import Scheduler

    _reset_defaultspack_singletons()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(tmp_path / "chat" / "conversations.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_COMPANY_STORE_PATH", str(tmp_path / "companies"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_MIMO_CODING_STATE_PATH", str(tmp_path / "mimo" / "state.json"))

    runtime = MimoCodingCompanyRuntime(pack_root=tmp_path / "ops_pack")
    status = runtime.bootstrap(
        start_nonstop=True,
        heartbeat_minutes=30,
        review_interval_minutes=180,
        qa_interval_minutes=240,
        model="stub/default",
        vision_model="stub/default",
        fast_model="stub/default",
        qa_targets=["http://127.0.0.1:3000"],
        docker_worker_count=0,
        max_tool_calls=0,
        seed_knowledge=False,
        run_initial_review_now=False,
    )

    docker_swarm = status["harness"]["docker_swarm"]
    assert status["harness"]["max_tool_calls"] is None
    assert docker_swarm["enabled"] is False
    assert docker_swarm["worker_count"] == 0
    assert docker_swarm["workers"] == []
    assert "compose_path" not in docker_swarm
    assert status["harness"]["qa_swarm_plan"]["workers"][0]["worker_id"] == "local-1"
    assert status["harness"]["qa_swarm_plan"]["workers"][0]["qa_target"] == "http://127.0.0.1:3000"
    for schedule in status["schedules"]:
        tool_policy = schedule["task"]["tool_policy"]
        permission_policy = tool_policy["tool_permission_policy"]
        assert tool_policy["max_tool_calls"] is None
        assert permission_policy["audit"] is True
        assert permission_policy["risk_defaults"]["high"] == "allow"
        assert permission_policy["unknown_tool_mode"] == "ask"
        assert permission_policy["missing_capability_mode"] == "deny"
        assert permission_policy["tools"]["coding_file_delete"] == "ask"
        assert permission_policy["tools"]["coding_file_restore"] == "ask"
        Scheduler().delete_schedule(schedule["id"])
    _reset_defaultspack_singletons()


def test_mimo_coding_company_rebootstrap_refreshes_existing_schedule_messages(tmp_path, monkeypatch):
    from ecosystem.rumi_operations_company_pack.domain.agent.mimo_coding_company import MimoCodingCompanyRuntime
    from domain.agent.scheduler import Scheduler

    _reset_defaultspack_singletons()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(tmp_path / "chat" / "conversations.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_COMPANY_STORE_PATH", str(tmp_path / "companies"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_MIMO_CODING_STATE_PATH", str(tmp_path / "mimo" / "state.json"))

    runtime = MimoCodingCompanyRuntime(pack_root=tmp_path / "ops_pack")
    first = runtime.bootstrap(
        start_nonstop=True,
        heartbeat_minutes=30,
        review_interval_minutes=180,
        qa_interval_minutes=240,
        model="stub/default",
        vision_model="stub/default",
        fast_model="stub/default",
        qa_targets=["http://127.0.0.1:3000"],
        docker_personas=["first_time_user"],
        seed_knowledge=False,
        run_initial_review_now=False,
    )
    qa_schedule_id = next(
        schedule["id"]
        for schedule in first["schedules"]
        if schedule["task"]["metadata"]["loop_key"] == "qa_loop"
    )

    second = runtime.bootstrap(
        start_nonstop=True,
        heartbeat_minutes=30,
        review_interval_minutes=120,
        qa_interval_minutes=90,
        model="stub/default",
        vision_model="stub/default",
        fast_model="stub/default",
        qa_targets=["http://127.0.0.1:3001"],
        docker_personas=["power_user", "impatient_user"],
        seed_knowledge=False,
        run_initial_review_now=False,
    )
    qa_schedule = next(
        schedule
        for schedule in second["schedules"]
        if schedule["task"]["metadata"]["loop_key"] == "qa_loop"
    )
    improvement_schedule = next(
        schedule
        for schedule in second["schedules"]
        if schedule["task"]["metadata"]["loop_key"] == "improvement_loop"
    )

    assert qa_schedule["id"] == qa_schedule_id
    assert "http://127.0.0.1:3001" in qa_schedule["task"]["message"]
    assert "Power user" in qa_schedule["task"]["message"]
    assert qa_schedule["config"] == {"value": 90, "unit": "minutes"}
    assert improvement_schedule["config"] == {"value": 120, "unit": "minutes"}
    assert second["harness"]["qa_swarm_plan"]["workers"][0]["persona_id"] == "power_user"
    assert second["harness"]["qa_swarm_plan"]["workers"][0]["qa_target"] == "http://127.0.0.1:3001"
    assert second["harness"]["docker_swarm"]["project_name"] == first["harness"]["docker_swarm"]["project_name"]
    assert second["harness"]["docker_swarm"]["workers"][0]["container_name"] == first["harness"]["docker_swarm"]["workers"][0]["container_name"]
    assignment = json.loads(Path(second["harness"]["docker_swarm"]["workers"][0]["assignment_path"]).read_text(encoding="utf-8"))
    compose_text = Path(second["harness"]["docker_swarm"]["compose_path"]).read_text(encoding="utf-8")
    assert assignment["persona_id"] == "power_user"
    assert assignment["qa_target"] == "http://127.0.0.1:3001"
    assert "http://127.0.0.1:3001" in compose_text
    assert "rumi.project_name" in compose_text

    for schedule in second["schedules"]:
        Scheduler().delete_schedule(schedule["id"])
    _reset_defaultspack_singletons()


def test_mimo_coding_company_rebootstrap_replenishes_completed_stream_task(tmp_path, monkeypatch):
    from ecosystem.rumi_operations_company_pack.domain.agent.mimo_coding_company import MimoCodingCompanyRuntime
    from domain.agent.scheduler import Scheduler
    from domain.company.task_store import CompanyTaskStore

    _reset_defaultspack_singletons()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(tmp_path / "chat" / "conversations.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_COMPANY_STORE_PATH", str(tmp_path / "companies"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_MIMO_CODING_STATE_PATH", str(tmp_path / "mimo" / "state.json"))

    runtime = MimoCodingCompanyRuntime(pack_root=tmp_path / "ops_pack")
    first = runtime.bootstrap(
        start_nonstop=True,
        heartbeat_minutes=30,
        review_interval_minutes=180,
        qa_interval_minutes=240,
        model="stub/default",
        vision_model="stub/default",
        fast_model="stub/default",
        seed_knowledge=False,
        run_initial_review_now=False,
    )
    stream_task_id = first["harness"]["stream_task_ids"]["provider_search_coverage"]
    store = CompanyTaskStore()
    updated = store.update(
        "mimo-coding-company",
        stream_task_id,
        {"status": "completed"},
    )
    assert updated is not None and updated["status"] == "completed"

    second = runtime.bootstrap(
        start_nonstop=True,
        heartbeat_minutes=30,
        review_interval_minutes=180,
        qa_interval_minutes=240,
        model="stub/default",
        vision_model="stub/default",
        fast_model="stub/default",
        seed_knowledge=False,
        run_initial_review_now=False,
    )
    replacement_task_id = second["harness"]["stream_task_ids"]["provider_search_coverage"]
    queued_tasks = store.list("mimo-coding-company", status="queued", limit=50, offset=0)

    assert replacement_task_id != stream_task_id
    assert second["harness"]["open_task_count"] == 6
    assert queued_tasks is not None and queued_tasks[1] == 6

    for schedule in second["schedules"]:
        Scheduler().delete_schedule(schedule["id"])
    _reset_defaultspack_singletons()


def test_mimo_coding_company_status_aggregates_worker_runtime_status(tmp_path, monkeypatch):
    from ecosystem.rumi_operations_company_pack.domain.agent.mimo_coding_company import MimoCodingCompanyRuntime
    from domain.agent.scheduler import Scheduler

    _reset_defaultspack_singletons()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(tmp_path / "chat" / "conversations.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_COMPANY_STORE_PATH", str(tmp_path / "companies"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_MIMO_CODING_STATE_PATH", str(tmp_path / "mimo" / "state.json"))

    runtime = MimoCodingCompanyRuntime(pack_root=tmp_path / "ops_pack")
    first = runtime.bootstrap(
        start_nonstop=True,
        heartbeat_minutes=30,
        review_interval_minutes=180,
        qa_interval_minutes=240,
        model="stub/default",
        vision_model="stub/default",
        fast_model="stub/default",
        qa_targets=["http://127.0.0.1:3000"],
        seed_knowledge=False,
        run_initial_review_now=False,
    )
    worker = first["harness"]["docker_swarm"]["workers"][0]
    status_path = Path(worker["status_path"])
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(
        json.dumps(
            {
                "worker_id": worker["worker_id"],
                "persona_id": worker["persona_id"],
                "started_at": "2026-05-27T00:00:00Z",
                "assignment": {
                    "worker_id": worker["worker_id"],
                    "persona_id": worker["persona_id"],
                },
                "browser_launch": {"attempted": True, "start_url": "http://127.0.0.1:3000"},
                "display": ":99",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    second = runtime.status()
    monitoring = second["harness"]["docker_swarm"]["monitoring"]
    supervisor = json.loads(Path(second["harness"]["docker_swarm"]["supervisor_path"]).read_text(encoding="utf-8"))

    assert monitoring["total_workers"] == len(second["harness"]["docker_swarm"]["workers"])
    assert monitoring["reported_workers"] == 1
    assert monitoring["browser_launch_attempted_workers"] == 1
    assert monitoring["workers"][0]["assignment_match"] is True
    assert second["company"]["metadata"]["docker_swarm"]["monitoring"]["reported_workers"] == 1
    assert supervisor["monitoring"]["reported_workers"] == 1
    assert supervisor["workers"][0]["container_name"] == second["harness"]["docker_swarm"]["workers"][0]["container_name"]
    assert supervisor["commands"]["supervisor"].startswith("cat ")

    refreshed = runtime.bootstrap(
        start_nonstop=True,
        heartbeat_minutes=30,
        review_interval_minutes=180,
        qa_interval_minutes=240,
        model="stub/default",
        vision_model="stub/default",
        fast_model="stub/default",
        qa_targets=["http://127.0.0.1:3000"],
        seed_knowledge=False,
        run_initial_review_now=False,
    )
    heartbeat_schedule = next(schedule for schedule in refreshed["schedules"] if schedule["task"]["metadata"]["loop_key"] == "heartbeat")
    qa_schedule = next(schedule for schedule in refreshed["schedules"] if schedule["task"]["metadata"]["loop_key"] == "qa_loop")
    assert "1/3 workers reported status" in heartbeat_schedule["task"]["message"]
    assert "1/3 attempted browser launch" in qa_schedule["task"]["message"]

    for schedule in refreshed["schedules"]:
        Scheduler().delete_schedule(schedule["id"])
    _reset_defaultspack_singletons()


def test_mimo_coding_company_static_knowledge_and_docker_bundles_exist():
    from ecosystem.rumi_operations_company_pack.domain.agent.mimo_coding_company import MimoCodingCompanyRuntime

    runtime = MimoCodingCompanyRuntime()
    manifest = runtime.manifest()
    docker_paths = manifest["docker"]["template_paths"]
    knowledge_docs = manifest["knowledge_bundle"]["documents"]

    assert Path(docker_paths["compose"]).is_file()
    assert Path(docker_paths["dockerfile"]).is_file()
    assert Path(docker_paths["entrypoint"]).is_file()
    assert Path(docker_paths["personas"]).is_file()
    assert knowledge_docs
    assert all(Path(path).is_file() for path in knowledge_docs)


def test_mimo_coding_company_manifest_expands_catalog_backed_groq_and_cerebras_models():
    from domain.ai_client.providers import get_all_known_models
    from ecosystem.rumi_operations_company_pack.domain.agent.mimo_coding_company import MimoCodingCompanyRuntime

    runtime = MimoCodingCompanyRuntime()
    allowlist = set(runtime.manifest()["model_self_selection"]["allowlist"])

    expected = {
        str(model.get("qualified_model_id") or model.get("id"))
        for provider_id in ("groq", "cerebras")
        for model in get_all_known_models(provider_id=provider_id)
        if isinstance(model, dict) and str(model.get("type") or "chat").strip().lower() in {"", "chat", "reasoning"}
    }

    assert "groq/openai/gpt-oss-20b" in allowlist
    assert "cerebras/zai-glm-4.7" in allowlist
    assert expected <= allowlist


def test_mimo_coding_company_bootstrap_block_accepts_catalog_backed_models(tmp_path, monkeypatch):
    from ecosystem.rumi_operations_company_pack.blocks.agent.mimo_company import bootstrap
    from domain.agent.scheduler import Scheduler

    _reset_defaultspack_singletons()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(tmp_path / "chat" / "conversations.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_COMPANY_STORE_PATH", str(tmp_path / "companies"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_MIMO_CODING_STATE_PATH", str(tmp_path / "mimo" / "state.json"))

    result = bootstrap.run(
        {
            "start_nonstop": True,
            "heartbeat_minutes": 30,
            "review_interval_minutes": 180,
            "qa_interval_minutes": 240,
            "model": "groq/openai/gpt-oss-20b",
            "vision_model": "stub/default",
            "fast_model": "cerebras/zai-glm-4.7",
            "seed_knowledge": False,
            "run_initial_review_now": False,
        },
        {},
    )

    assert result["status"] == "ok"
    assert result["data"]["harness"]["main_model"] == "groq/openai/gpt-oss-20b"
    assert result["data"]["harness"]["fast_model"] == "cerebras/zai-glm-4.7"

    for schedule in result["data"]["schedules"]:
        Scheduler().delete_schedule(schedule["id"])
    _reset_defaultspack_singletons()


def test_mimo_coding_company_bootstrap_block_accepts_zero_for_unlimited_and_non_docker(tmp_path, monkeypatch):
    from ecosystem.rumi_operations_company_pack.blocks.agent.mimo_company import bootstrap
    from domain.agent.scheduler import Scheduler

    _reset_defaultspack_singletons()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(tmp_path / "chat" / "conversations.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_COMPANY_STORE_PATH", str(tmp_path / "companies"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_MIMO_CODING_STATE_PATH", str(tmp_path / "mimo" / "state.json"))

    result = bootstrap.run(
        {
            "start_nonstop": True,
            "model": "stub/default",
            "vision_model": "stub/default",
            "fast_model": "stub/default",
            "max_tool_calls": 0,
            "docker_worker_count": 0,
            "seed_knowledge": False,
            "run_initial_review_now": False,
        },
        {},
    )

    assert result["status"] == "ok"
    assert result["data"]["harness"]["max_tool_calls"] is None
    assert result["data"]["harness"]["docker_swarm"]["enabled"] is False
    assert result["data"]["harness"]["docker_swarm"]["worker_count"] == 0
    for schedule in result["data"]["schedules"]:
        assert schedule["task"]["tool_policy"]["max_tool_calls"] is None
        Scheduler().delete_schedule(schedule["id"])
    _reset_defaultspack_singletons()


def test_mimo_coding_conversation_resolves_pack_system_prompt():
    from blocks.chat.send import _conversation_system_prompt
    from domain.prompt.manager import get_manager

    prompt = _conversation_system_prompt({"system_prompt_id": "mimo_coding_company"}, get_manager())

    assert "MiMo Coding Company" in prompt
    assert "Toolsmith builds missing tools or skills instead of stopping" in prompt


def test_operations_heartbeat_trigger_persists_into_single_client_conversation(tmp_path, monkeypatch):
    from ecosystem.rumi_operations_company_pack.domain.agent.operations_company import OperationsCompanyRuntime
    from domain.agent.scheduler import Scheduler
    from domain.chat.store import ChatStore

    _reset_defaultspack_singletons()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(tmp_path / "chat" / "conversations.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_OPERATIONS_STATE_PATH", str(tmp_path / "ops" / "state.json"))

    status = OperationsCompanyRuntime().bootstrap(start_nonstop=True, heartbeat_minutes=30, model="stub/default")
    conversation_id = status["conversation_id"]
    schedule_id = status["schedules"][0]["id"]

    result = Scheduler().trigger_now(schedule_id)

    assert result["status"] == "completed"
    conversation = ChatStore().get_conversation(conversation_id)
    roles = [message["role"] for message in conversation["messages"]]
    assert roles == ["user", "assistant"]
    assert conversation["messages"][0]["metadata"]["source"] == "scheduler"
    assert conversation["messages"][0]["metadata"]["profile_id"] == "defaultspack.operations_company"

    persisted = json.loads((tmp_path / "chat" / "conversations.json").read_text(encoding="utf-8"))
    assert persisted["conversations"][conversation_id]["messages"][0]["metadata"]["schedule_id"] == schedule_id

    Scheduler().delete_schedule(schedule_id)
    _reset_defaultspack_singletons()


def test_rumi_api_tool_lists_routes_and_requires_mutation_approval():
    from ecosystem.rumi_default_tools_pack.domain.tool.rumi_api import run

    listed = run({"action": "list_routes"}, {})
    mutation = run(
        {
            "action": "request",
            "method": "POST",
            "path": "/api/agent/company/bootstrap",
            "body": {"start_nonstop": True},
            "allow_mutation": True,
        },
        {"profile_policy": {"yolo_mode": False}},
    )

    assert listed["status"] == "ok"
    assert any(route["path"] == "/api/agent/company/status" for route in listed["data"]["routes"])
    assert any(route["path"] == "/api/agent/mimo-company/status" for route in listed["data"]["routes"])
    assert mutation["status"] == "ok"
    assert mutation["data"]["approval_required"] is True
