from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def _reset_agent_studio_state() -> None:
    from domain.agent_runtime.run_store import AgentRunStore
    from domain.chat.store import ChatStore
    from domain.company.runtime_store import CompanyRuntimeStore
    from domain.company.store import CompanyStore

    AgentRunStore._instance = None
    ChatStore._instance = None
    CompanyRuntimeStore._instance = None
    CompanyStore._instance = None


def test_agent_studio_profile_activation_enforces_human_only_and_review_gate(tmp_path, monkeypatch):
    from domain.agent_studio.service import AgentStudioService
    from domain.chat.store import ChatStore

    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(tmp_path / "chat" / "conversations.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_COMPANY_STORE_PATH", str(tmp_path / "companies"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_COMPANY_RUNTIME_DB_PATH", str(tmp_path / "company_runtime.db"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_STUDIO_PATH", str(tmp_path / "agent_studio.json"))
    _reset_agent_studio_state()

    store = ChatStore()
    conversation = store.create_conversation(model="stub/default")
    service = AgentStudioService()

    result = service.activate_profile_for_conversation(conversation["id"], "builtin.coding")
    updated = result["conversation"]

    assert updated["metadata"]["agent_profile_id"] == "builtin.coding"
    assert updated["metadata"]["agent_studio"]["surface"] == "mode_agent"
    assert updated["metadata"]["agent_studio"]["active_profile_id"] == "builtin.coding"
    assert updated["metadata"]["agent_studio"]["review_gate"]["approved"] is False
    assert updated["metadata"]["agent_studio"]["activity_log"][0]["type"] == "activation"

    yolo_guard = service.command_guard("yolo", conversation_id=conversation["id"])
    commit_guard = service.command_guard("commit", conversation_id=conversation["id"])

    assert yolo_guard["allowed"] is False
    assert yolo_guard["code"] == "HUMAN_ONLY_COMMAND"
    assert commit_guard["allowed"] is False
    assert commit_guard["code"] == "REVIEW_GATE_BLOCKED"

    service.mark_review_gate_for_conversation(conversation["id"], approved=True, approved_by="test-reviewer")
    approved_commit_guard = service.command_guard("commit", conversation_id=conversation["id"])
    refreshed = store.get_conversation(conversation["id"])
    activity_log = refreshed["metadata"]["agent_studio"]["activity_log"]
    activity_types = {entry["type"] for entry in activity_log}
    denial_codes = {entry.get("reason_code") for entry in activity_log if entry.get("type") == "command_denied"}

    assert approved_commit_guard["allowed"] is True
    assert approved_commit_guard.get("warning") in {None, ""}
    assert {"activation", "command_denied", "review_gate"} <= activity_types
    assert {"HUMAN_ONLY_COMMAND", "REVIEW_GATE_BLOCKED"} <= denial_codes


def test_agent_studio_team_and_fusion_activation_materialize_workroom_members(tmp_path, monkeypatch):
    from domain.agent_studio.service import AgentStudioService
    from domain.chat.store import ChatStore

    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(tmp_path / "chat" / "conversations.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_COMPANY_STORE_PATH", str(tmp_path / "companies"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_COMPANY_RUNTIME_DB_PATH", str(tmp_path / "company_runtime.db"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_STUDIO_PATH", str(tmp_path / "agent_studio.json"))
    _reset_agent_studio_state()

    store = ChatStore()
    team_conversation = store.create_conversation(model="stub/default")
    fusion_conversation = store.create_conversation(model="stub/default")
    service = AgentStudioService()

    team_result = service.activate_team_for_conversation(team_conversation["id"], "builtin.delivery_team")
    fusion_result = service.activate_fusion_for_conversation(fusion_conversation["id"], "builtin.delivery_fusion")

    team_company = team_result["company"]
    fusion_company = fusion_result["company"]

    assert team_result["conversation"]["metadata"]["agent_studio"]["surface"] == "team_agent"
    assert team_result["conversation"]["metadata"]["team_id"] == "builtin.delivery_team"
    assert team_company["metadata"]["team_id"] == "builtin.delivery_team"
    assert {"builtin_coding", "builtin_research", "builtin_review"}.issubset(team_company["agents"].keys())

    assert fusion_result["conversation"]["metadata"]["agent_studio"]["surface"] == "fusion_agent"
    assert fusion_result["conversation"]["metadata"]["fusion_id"] == "builtin.delivery_fusion"
    assert fusion_company["metadata"]["fusion_id"] == "builtin.delivery_fusion"
    assert {"builtin_coding", "builtin_research", "builtin_review"}.issubset(fusion_company["agents"].keys())


def test_agent_studio_import_export_round_trip_preserves_list_exports(tmp_path, monkeypatch):
    from domain.agent_studio.service import AgentStudioService

    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_STUDIO_PATH", str(tmp_path / "agent_studio.json"))
    _reset_agent_studio_state()

    service = AgentStudioService()
    service.upsert_profile(
        {
            "id": "custom.frontend.qa",
            "display_name": "Frontend QA",
            "base_profile_id": "rumi_frontend_design.frontend_design_reviewer",
            "aliases": ["frontend-qa"],
        }
    )
    service.upsert_team(
        {
            "id": "custom.frontend.team",
            "display_name": "Frontend Team",
            "coordinator_profile_id": "custom.frontend.qa",
            "member_profile_ids": ["custom.frontend.qa", "builtin.review"],
        }
    )
    service.upsert_fusion(
        {
            "id": "custom.frontend.fusion",
            "display_name": "Frontend Fusion",
            "participant_profile_ids": ["custom.frontend.qa", "builtin.review"],
            "synthesis_profile_id": "builtin.review",
        }
    )

    exported = service.export_bundle()
    service.store.replace({})
    imported = service.import_bundle(exported)

    assert imported["profiles"]["custom.frontend.qa"]["id"] == "custom.frontend.qa"
    assert imported["teams"]["custom.frontend.team"]["id"] == "custom.frontend.team"
    assert imported["fusions"]["custom.frontend.fusion"]["id"] == "custom.frontend.fusion"
    assert service.resolve_profile("custom.frontend.qa") is not None
    assert service.resolve_team("custom.frontend.team") is not None
    assert service.resolve_fusion("custom.frontend.fusion") is not None


def test_agent_studio_import_bundle_validation_rejects_unknown_member_profiles(tmp_path, monkeypatch):
    from domain.agent_studio.service import AgentStudioService

    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_STUDIO_PATH", str(tmp_path / "agent_studio.json"))
    _reset_agent_studio_state()

    service = AgentStudioService()

    try:
        service.import_bundle(
            {
                "teams": [
                    {
                        "id": "broken.team",
                        "member_profile_ids": ["missing.profile"],
                    }
                ]
            }
        )
    except ValueError as exc:
        assert "unknown profile" in str(exc)
    else:
        raise AssertionError("expected invalid bundle import to raise ValueError")


def test_agent_studio_builtin_frontend_and_mini_profiles_are_resolvable(tmp_path, monkeypatch):
    from domain.agent_studio.service import AgentStudioService

    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_STUDIO_PATH", str(tmp_path / "agent_studio.json"))
    _reset_agent_studio_state()

    service = AgentStudioService()

    frontend = service.resolve_profile("frontend")
    mini = service.resolve_profile("mini")

    assert frontend is not None
    assert frontend["id"] == "builtin.frontend"
    assert mini is not None
    assert mini["id"] == "builtin.mini_coding"
def test_agent_studio_preview_selection_returns_structured_router_decision(tmp_path, monkeypatch):
    from domain.agent_studio.service import AgentStudioService

    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_STUDIO_PATH", str(tmp_path / "agent_studio.json"))
    _reset_agent_studio_state()

    service = AgentStudioService()
    service.replace_selection_rules(
        [
            {
                "display_name": "Frontend Polish",
                "target_type": "profile",
                "target_id": "builtin.frontend",
                "prompt_contains": ["frontend", "css"],
                "condition_prompt": "responsive layout polish",
                "requires_confirmation": True,
                "reason": "Use the frontend specialist for UI cleanup.",
            }
        ]
    )

    decision = service.preview_selection("Please polish this frontend css layout for mobile.")

    assert decision["selected"] is True
    assert decision["selected_profile_id"] == "builtin.frontend"
    assert decision["selected_target_type"] == "profile"
    assert decision["rule_display_name"] == "Frontend Polish"
    assert decision["requires_confirmation"] is True
    assert any(code.startswith("prompt_contains:") for code in decision["reason_codes"])
    assert decision["confidence"] > 0.4


def test_agent_studio_auto_select_applies_profile_and_records_router_activity(tmp_path, monkeypatch):
    from domain.agent_studio.service import AgentStudioService
    from domain.chat.store import ChatStore

    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(tmp_path / "chat" / "conversations.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_COMPANY_STORE_PATH", str(tmp_path / "companies"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_COMPANY_RUNTIME_DB_PATH", str(tmp_path / "company_runtime.db"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_STUDIO_PATH", str(tmp_path / "agent_studio.json"))
    _reset_agent_studio_state()

    store = ChatStore()
    conversation = store.create_conversation(model="stub/default")
    service = AgentStudioService()
    service.update_settings({"selection_defaults": {"auto_select": True}})
    service.replace_selection_rules(
        [
            {
                "display_name": "Reviewer Route",
                "target_type": "profile",
                "target_id": "builtin.review",
                "match_terms": ["review", "bug"],
            }
        ]
    )

    result = service.auto_select_for_conversation(conversation["id"], "Please review this for bugs before commit.")
    updated = result["conversation"]
    activity_types = {entry["type"] for entry in updated["metadata"]["agent_studio"]["activity_log"]}

    assert result["applied"] is True
    assert result["decision"]["selected_profile_id"] == "builtin.review"
    assert updated["metadata"]["agent_studio"]["active_profile_id"] == "builtin.review"
    assert updated["metadata"]["agent_studio"]["activation_reason"].startswith("auto_select:")
    assert {"activation", "selection_router"} <= activity_types


def test_agent_studio_selection_rule_history_snapshots_previous_rules(tmp_path, monkeypatch):
    from domain.agent_studio.service import AgentStudioService

    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_STUDIO_PATH", str(tmp_path / "agent_studio.json"))
    _reset_agent_studio_state()

    service = AgentStudioService()
    service.replace_selection_rules(
        [
            {
                "display_name": "Initial Review Route",
                "target_type": "profile",
                "target_id": "builtin.review",
                "match_terms": ["review"],
            }
        ]
    )
    service.replace_selection_rules(
        [
            {
                "display_name": "Frontend Route",
                "target_type": "profile",
                "target_id": "builtin.frontend",
                "match_terms": ["frontend"],
            }
        ]
    )

    manifest = service.manifest()
    history = manifest["selection_rule_history"]

    assert len(history) >= 1
    assert history[0]["rule_count"] == 1
    assert history[0]["rules"][0]["target_id"] == "builtin.review"
