from __future__ import annotations

from pathlib import Path


PACK_ROOT = Path(__file__).resolve().parent.parent / "ecosystem" / "defaultspack"


def test_agent_service_default_files_are_present():
    expected = [
        "docs/ai_agent_services_feature_catalog.md",
        "docs/local_agent_implementation_plan.md",
        "docs/local_first_policy.md",
        "schemas/agent_plan.schema.yaml",
        "schemas/tool_call.schema.yaml",
        "capabilities/local_file.capability.yaml",
        "capabilities/safety.capability.yaml",
        "profiles/local_agent.profile.yaml",
        "prompts/local_agent.system.md",
        "presets/local_only_safe.preset.yaml",
        "examples/local_agent_project.example.yaml",
    ]
    missing = [path for path in expected if not (PACK_ROOT / path).is_file()]
    assert missing == []


def test_capability_catalog_loads_and_filters_local_first_capabilities():
    from ecosystem.defaultspack.domain.capability.catalog import CapabilityCatalog

    catalog = CapabilityCatalog(PACK_ROOT)
    capabilities = catalog.list_capabilities()
    capability_ids = {item["id"] for item in capabilities}

    assert {"local_file", "terminal", "git", "memory", "artifact", "compact", "research", "safety"} <= capability_ids
    assert catalog.get("local_file")["requires_approval"] is True
    assert all(item["local_only"] is True for item in catalog.list_capabilities(local_only=True))
    assert catalog.summary()["count"] >= 11


def test_capability_blocks_return_manifest_and_filters():
    from ecosystem.defaultspack.blocks.capability import list as list_block
    from ecosystem.defaultspack.blocks.capability import manifest

    listed = list_block.run({"local_only": True}, {})
    assert listed["status"] == "ok"
    assert listed["data"]["count"] >= 1
    assert all(item["local_only"] is True for item in listed["data"]["capabilities"])

    single = manifest.run({"capability_id": "terminal"}, {})
    assert single["status"] == "ok"
    assert single["data"]["capability"]["id"] == "terminal"


def test_frontend_catalog_exposes_capability_sidebar_items():
    from ecosystem.defaultspack.domain.frontend.registry import FrontendRegistry

    catalog = FrontendRegistry(PACK_ROOT).build_catalog()
    items = catalog["sidebar"]["items"]

    assert any(item["category"] == "capability" and item["id"] == "capability-local_file" for item in items)
    assert any(section["id"] == "capabilities" for section in catalog["settings"]["sections"])


def test_local_research_report_can_return_unsaved_report():
    from ecosystem.defaultspack.blocks.research.report import run

    result = run({"query": "local first", "save": False}, {})

    assert result["status"] == "ok"
    assert result["data"]["query"] == "local first"
    assert result["data"]["artifact"] is None
    assert result["data"]["report"].startswith("# Research Report: local first")
