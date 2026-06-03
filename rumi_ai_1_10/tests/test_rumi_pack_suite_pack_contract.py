from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from ecosystem.setup_pack.pack_selector import PackSelector

ROOT = Path(__file__).resolve().parent.parent
PACK_ID = "rumi_pack_suite_pack"
PACK_DIR = ROOT / "ecosystem" / PACK_ID
SETUP_PACK_JSON = ROOT / "ecosystem" / "setup_pack" / PACK_ID / "pack.json"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_pack_suite_required_assets_and_metadata() -> None:
    required = [
        "README.md", "docs/README.md", "docs/architecture.md", "docs/interfaces.md", "docs/operations.md", "ecosystem.json",
        "catalog/bundles.pack_suite.yaml", "catalog/overlap_matrix.pack_suite.yaml", "catalog/defaultspack_promotion_matrix.yaml",
        "policies/suite_selection_policy.yaml", "profiles/pack_suite_curator.profile.yaml", "prompts/pack_suite_curator.system.md",
        "presets/all_agent_capabilities.preset.yaml", "presets/defaultspack_candidate_review.preset.yaml",
        "examples/choose_browser_bundle.example.yaml", "examples/promote_pack.example.yaml",
    ]
    assert [path for path in required if not (PACK_DIR / path).is_file()] == []
    ecosystem = read_json(PACK_DIR / "ecosystem.json")
    assert ecosystem["pack_identity"] == f"rumi:ecosystem/{PACK_ID}"
    assert ecosystem["metadata"]["required_secrets"] == []
    assert ecosystem["metadata"]["network_policy"] == "none_by_default"
    assert ecosystem["metadata"]["executable_code"] is False
    assert len(ecosystem["optional_integrations"]) >= 12


def test_pack_suite_yaml_parses_and_has_expected_bundles() -> None:
    for path in PACK_DIR.rglob("*.yaml"):
        assert isinstance(yaml.safe_load(path.read_text(encoding="utf-8")), dict), path
    bundles = yaml.safe_load((PACK_DIR / "catalog" / "bundles.pack_suite.yaml").read_text(encoding="utf-8"))
    bundle_ids = {bundle["bundle_id"] for bundle in bundles["bundles"]}
    assert {"coding_operator", "research_workspace", "browser_operator", "personal_agent_os", "integration_gateway"} <= bundle_ids
    matrix = yaml.safe_load((PACK_DIR / "catalog" / "overlap_matrix.pack_suite.yaml").read_text(encoding="utf-8"))
    assert matrix["surfaces"]["browser_semantic_dom"] == "rumi_browser_element_pack"
    assert matrix["surfaces"]["schedules_and_wakeups"] == "rumi_workflow_scheduler_pack"


def test_pack_suite_setup_pack_discoverable_and_advisory_only() -> None:
    setup = read_json(SETUP_PACK_JSON)
    candidate = {item.pack_id: item for item in PackSelector(ROOT / "ecosystem").scan_candidates()}[PACK_ID]
    assert setup["supports_all_ok"] is False
    assert setup["risk_level"] == "low"
    assert candidate.depends_on == [{"pack_id": "defaultspack", "version": ">=2.0.0"}]
    assert candidate.overlap_policy["bundle_selection"] == "advisory_only_no_runtime_override"
    assert candidate.defaultspack_promotion["eligible"] is False


def test_pack_suite_docs_no_secrets_and_explain_promotion() -> None:
    docs = "\n".join(
        (PACK_DIR / path).read_text(encoding="utf-8")
        for path in ["README.md", "docs/interfaces.md", "docs/operations.md"]
    )
    for expected in ["Required Secrets", "None", "defaultspack", "promotion", "bundle", "overlap"]:
        assert expected in docs
    pattern = re.compile(
        r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{12,}"
    )
    checked = [p for p in PACK_DIR.rglob("*") if p.is_file()] + [SETUP_PACK_JSON]
    assert [str(p.relative_to(ROOT)) for p in checked if pattern.search(p.read_text(encoding="utf-8"))] == []
