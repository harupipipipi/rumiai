from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from ecosystem.setup_pack.pack_selector import PackSelector

ROOT = Path(__file__).resolve().parent.parent
PACK_ID = "rumi_sandbox_runtime_pack"
PACK_DIR = ROOT / "ecosystem" / PACK_ID
SETUP_PACK_JSON = ROOT / "ecosystem" / "setup_pack" / PACK_ID / "pack.json"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_pack_required_assets_and_metadata() -> None:
    required = [
        "README.md",
        "docs/README.md",
        "docs/architecture.md",
        "docs/interfaces.md",
        "docs/operations.md",
        "ecosystem.json",
        "catalog/runtime_matrix.yaml",
        "policies/sandbox_execution.policy.yaml",
        "profiles/sandbox_runtime_reviewer.profile.yaml",
        "prompts/sandbox_runtime_reviewer.system.md",
        "presets/safe_default.preset.yaml",
        "presets/handoff_review.preset.yaml",
        "presets/quality_gate.preset.yaml",
        "examples/container_test_run.example.yaml",
    ]
    assert [path for path in required if not (PACK_DIR / path).is_file()] == []
    ecosystem = read_json(PACK_DIR / "ecosystem.json")
    assert ecosystem["pack_identity"] == f"rumi:ecosystem/{PACK_ID}"
    assert ecosystem["metadata"]["required_secrets"] == []
    assert ecosystem["metadata"]["network_policy"] == "none_by_default"
    assert ecosystem["metadata"]["executable_code"] is False
    assert ecosystem["metadata"]["owner_surfaces"]


def test_pack_yaml_json_assets_parse() -> None:
    for path in PACK_DIR.rglob("*.yaml"):
        assert isinstance(yaml.safe_load(path.read_text(encoding="utf-8")), dict), path
    for path in PACK_DIR.rglob("*.json"):
        assert isinstance(json.loads(path.read_text(encoding="utf-8")), dict), path


def test_pack_setup_discoverable_and_overlap_scoped() -> None:
    setup = read_json(SETUP_PACK_JSON)
    candidate = {item.pack_id: item for item in PackSelector(ROOT / "ecosystem").scan_candidates()}[PACK_ID]
    assert setup["supports_all_ok"] is False
    assert setup["risk_level"] == "high"
    assert candidate.depends_on == [{'pack_id': 'defaultspack', 'version': '>=2.0.0'}]
    assert candidate.overlap_policy["code_execution"] == "requires_defaultspack_tool_grants"
    assert candidate.defaultspack_promotion["eligible"] is False


def test_pack_docs_no_secrets_and_explain_boundaries() -> None:
    docs = "\n".join((PACK_DIR / path).read_text(encoding="utf-8") for path in ["README.md", "docs/interfaces.md", "docs/operations.md"])
    for expected in ["Required Secrets", "None", "defaultspack", "handoff", "evidence"]:
        assert expected in docs
    pattern = re.compile(
        r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*[\'\"]?[A-Za-z0-9_\-]{12,}"
    )
    checked = [p for p in PACK_DIR.rglob("*") if p.is_file()] + [SETUP_PACK_JSON]
    assert [str(p.relative_to(ROOT)) for p in checked if pattern.search(p.read_text(encoding="utf-8"))] == []
