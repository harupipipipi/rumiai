from __future__ import annotations

import pytest

pytestmark = pytest.mark.contract

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_runtime_router_keeps_computer_use_as_last_operation_layer() -> None:
    from core_runtime.supervisor_dashboard import build_runtime_router_contract

    router = build_runtime_router_contract()

    assert router["structured_first"] is True
    assert router["computer_use_role"] == "last_operation_layer"
    assert router["preferred_order"][0] == "shell"
    assert "computer_use" not in router["preferred_order"]
    assert router["fallback_order"][-1] == "computer_use"


def test_supervisor_catalog_is_cloud_first_without_docker_desktop_requirement() -> None:
    from core_runtime.supervisor_dashboard import build_supervisor_dashboard_snapshot

    snapshot = build_supervisor_dashboard_snapshot(run_store=None)
    providers = {provider["id"]: provider for provider in snapshot["sandbox_providers"]}

    assert providers["cloud"]["default"] is True
    assert providers["cloud"]["install_required"] is False
    assert "browserbase" in providers["cloud"]["providers"]
    assert "docker_sbx" in providers["local_packaged"]["providers"]
    assert "docker_desktop" not in providers["local_packaged"]["providers"]
    assert "docker_desktop" in providers["byo_advanced"]["providers"]


def test_supervisor_snapshot_summarizes_agent_runtime_store(tmp_path) -> None:
    from core_runtime.supervisor_dashboard import build_supervisor_dashboard_snapshot
    from domain.agent_runtime.models import AgentRun
    from domain.agent_runtime.run_store import AgentRunStore

    store = AgentRunStore(tmp_path / "agent_runtime.db")
    store.upsert_run(
        AgentRun(
            run_id="run_wait",
            session_key="agent:reviewer:main",
            task="Approve browser upload",
            status="waiting_approval",
            agent_id="reviewer",
            runtime_profile_json={"policy": {"risk": "high"}, "sandbox": {"provider": "browserbase"}},
            execution_json={
                "screen": {"available": True, "provider": "browserbase", "url": "https://live.example/session"},
                "replay": {"available": True, "url": "https://replay.example/session"},
                "artifacts": {"screenshots": ["one.png"], "logs": ["run.log"]},
            },
        )
    )
    store.upsert_run(
        AgentRun(
            run_id="run_stale",
            session_key="agent:coding_engineer:main",
            task="Old coding work",
            status="running",
            agent_id="coding_engineer",
            heartbeat_at="2000-01-01T00:00:00Z",
        )
    )
    store.add_event("run_wait", "approval_requested", {"tool": "browser_upload_file"})

    snapshot = build_supervisor_dashboard_snapshot(
        run_store=store,
        stale_after_seconds=1,
        event_limit=5,
    )

    assert snapshot["metrics"]["available"] is True
    assert snapshot["metrics"]["active_runs"] == 2
    assert snapshot["metrics"]["waiting_approvals"] == 1
    assert snapshot["metrics"]["stale_runs"] == 1
    assert snapshot["metrics"]["screen_sessions"] == 1
    assert snapshot["metrics"]["replay_ready"] == 1
    assert snapshot["selected_session"]["run_id"] == "run_wait"
    assert snapshot["selected_session"]["risk"] == "high"
    assert snapshot["recent_events"][0]["event_type"] == "approval_requested"


def test_panel_dashboard_includes_supervisor_snapshot(monkeypatch) -> None:
    from core_runtime.api.control_panel_handlers import ControlPanelHandlersMixin
    from core_runtime import supervisor_dashboard

    monkeypatch.setattr(
        supervisor_dashboard,
        "build_supervisor_dashboard_snapshot",
        lambda: {"router": {"policy": "structured_first_computer_last"}, "metrics": {"active_runs": 0}},
    )

    class FakePanel(ControlPanelHandlersMixin):
        def _panel_list_packs_internal(self):
            return [{"enabled": True}, {"enabled": False}]

        def _panel_list_flows_internal(self):
            return [{"flow_id": "flow_1"}]

        def _panel_read_profile(self):
            return {"username": "haru", "language": "ja", "icon": None}

    dashboard = FakePanel()._panel_get_dashboard()

    assert dashboard["packs"] == {"total": 2, "enabled": 1, "disabled": 1}
    assert dashboard["flows"] == {"total": 1}
    assert dashboard["supervisor"]["router"]["policy"] == "structured_first_computer_last"
