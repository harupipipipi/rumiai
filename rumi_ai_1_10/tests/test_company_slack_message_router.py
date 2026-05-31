from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def _reset(monkeypatch, tmp_path: Path) -> None:
    from domain.agent_runtime.run_store import AgentRunStore
    from domain.company.runtime_store import CompanyRuntimeStore
    from domain.company.store import CompanyStore

    monkeypatch.setenv("RUMI_DEFAULTSPACK_COMPANY_STORE_PATH", str(tmp_path / "companies"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_COMPANY_RUNTIME_DB_PATH", str(tmp_path / "company_runtime.db"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_RUNTIME_DIR", str(tmp_path / "agent_runtime"))
    CompanyStore._instance = None
    CompanyRuntimeStore._instance = None
    AgentRunStore._instance = None


def test_posting_mention_creates_message_task_and_delegate_run(monkeypatch, tmp_path):
    _reset(monkeypatch, tmp_path)
    from domain.company.message_router import CompanySlackRuntime
    from domain.company.service import CompanyService
    from domain.company.store import CompanyStore

    seen = {}

    def fake_dispatch(envelope, context):
        seen["action_id"] = envelope.delivery["action_id"]
        seen["agent_id"] = envelope.target["agent_id"]
        seen["context_agent_id"] = context["agent_id"]
        return {"status": "ok", "delegate": {"execution_id": "run_coder", "status": "running"}, "result": {"status": "running"}}

    monkeypatch.setattr("domain.company.run_dispatcher.dispatch_input", fake_dispatch)
    company = CompanyService().bootstrap_default_company()
    result = CompanySlackRuntime().post_message(
        company["id"],
        content="@coding_engineer fix this",
        sender_id="user",
    )

    assert result["message"]["content"] == "@coding_engineer fix this"
    assert result["task"]["source"] == "mention"
    assert result["task"]["target_agent_ids"] == ["coding_engineer"]
    assert result["routes"][0]["route"] == "agent.delegate"
    assert result["routes"][0]["dispatch"]["run_links"][0]["run_id"] == "run_coder"
    assert seen == {"action_id": "agent.delegate", "agent_id": "coding_engineer", "context_agent_id": "coding_engineer"}

    persisted = json.loads(CompanyStore().storage_file.read_text(encoding="utf-8"))
    assert persisted["companies"][company["id"]]["messages"] == {}
    assert persisted["companies"][company["id"]]["tasks"] == {}
