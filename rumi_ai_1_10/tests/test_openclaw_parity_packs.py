from __future__ import annotations

import json
from pathlib import Path

import yaml

from ecosystem.setup_pack.pack_selector import PackSelector


REQUIRED_PARITY_PACKS = {
    "rumi_agent_continuity_pack",
    "rumi_agent_services_pack",
    "rumi_agent_workroom_pack",
    "rumi_agentic_qa_pack",
    "rumi_api_toolsmith_pack",
    "rumi_artifact_app_runtime_pack",
    "rumi_browser_automation_pack",
    "rumi_browser_element_pack",
    "rumi_browser_form_operator_pack",
    "rumi_browser_session_replay_pack",
    "rumi_business_ops_pack",
    "rumi_code_ide_pack",
    "rumi_code_migration_pack",
    "rumi_computer_control_pack",
    "rumi_connector_gateway_pack",
    "rumi_customer_research_pack",
    "rumi_data_analysis_pack",
    "rumi_devops_release_pack",
    "rumi_doc_contract_rescue_pack",
    "rumi_document_intelligence_pack",
    "rumi_evidence_dossier_pack",
    "rumi_experiment_design_pack",
    "rumi_frontend_design_pack",
    "rumi_knowledge_marketplace_pack",
    "rumi_localization_pack",
    "rumi_mcp_gateway_pack",
    "rumi_meeting_intelligence_pack",
    "rumi_memory_knowledge_pack",
    "rumi_model_evals_pack",
    "rumi_multimodal_media_pack",
    "rumi_observability_pack",
    "rumi_office_authoring_pack",
    "rumi_omnichannel_agent_inbox_pack",
    "rumi_openclaw_parity_pack",
    "rumi_pack_suite_pack",
    "rumi_prompt_studio_pack",
    "rumi_research_pack",
    "rumi_runtime_benchmark_pack",
    "rumi_sandbox_runtime_pack",
    "rumi_security_review_pack",
    "rumi_sop_mining_pack",
    "rumi_study_coach_pack",
    "rumi_subagent_pr_manager_pack",
    "rumi_telephony_delegate_pack",
    "rumi_voice_mobile_pack",
    "rumi_workflow_scheduler_pack",
    "rumi_workspace_pack",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_openclaw_parity_setup_packs_are_discoverable() -> None:
    repo_root = _repo_root()
    candidates = {
        candidate.pack_id: candidate
        for candidate in PackSelector(repo_root / "ecosystem").scan_candidates()
    }

    missing = REQUIRED_PARITY_PACKS.difference(candidates)
    assert missing == set()

    for pack_id in REQUIRED_PARITY_PACKS:
        candidate = candidates[pack_id]
        target_pack_id = candidate.pack_id
        ecosystem_json = repo_root / "ecosystem" / target_pack_id / "ecosystem.json"
        assert ecosystem_json.is_file(), pack_id

        target = json.loads(ecosystem_json.read_text(encoding="utf-8"))
        assert target["pack_id"] == target_pack_id
        assert candidate.pack_identity == f"rumi:ecosystem/{target_pack_id}"
        assert candidate.marketplace["registry"] == "bundled"
        assert candidate.marketplace["publisher"] == "rumi-ai"
        assert candidate.marketplace["status"] == "verified"
        assert candidate.signing["mode"] == "repository_reviewed"
        assert candidate.signing["verified"] is True


def test_openclaw_surface_map_has_core_sections() -> None:
    catalog_path = (
        _repo_root()
        / "ecosystem"
        / "rumi_openclaw_parity_pack"
        / "catalog"
        / "openclaw_surface_map.yaml"
    )

    data = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    for key in (
        "channels",
        "plugins",
        "providers",
        "skills",
        "runtime_surfaces",
        "mapping_to_rumi_packs",
    ):
        assert data[key], key

    assert "rumi_omnichannel_agent_inbox_pack" in data["mapping_to_rumi_packs"].values()
    assert "rumi_model_catalog_pack" in data["mapping_to_rumi_packs"].values()
    assert "docs/agent-runtime-architecture.md" in data["sources"]["agent_runtime"]
