from __future__ import annotations

import json
from pathlib import Path

from core_runtime.flow_loader import FlowLoader


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
MANIFEST = REPO_ROOT / "tests" / "flow_corpus" / "manifest.json"


def _load_manifest() -> dict:
    if not MANIFEST.exists():
        raise AssertionError(
            "flow corpus manifest is missing. run "
            "`python rumi_ai_1_10/scripts/quality_pack/generate_flow_corpus.py` first."
        )
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_flow_corpus_valid_cases_load_successfully():
    manifest = _load_manifest()
    loader = FlowLoader()

    assert manifest["valid_count"] > 0
    assert len(manifest["valid"]) == manifest["valid_count"]

    for record in manifest["valid"]:
        flow_path = REPO_ROOT / record["file"]
        result = loader.load_flow_file(flow_path, "official")
        assert result.success, f"expected success for {flow_path}: {result.errors}"
        assert result.flow_def is not None
        assert result.flow_def.flow_id.startswith("corpus.valid.")
        assert len(result.flow_def.steps) >= 18
        assert len(result.flow_def.phases) >= 3


def test_flow_corpus_invalid_cases_fail_with_errors():
    manifest = _load_manifest()
    loader = FlowLoader()

    assert manifest["invalid_count"] > 0
    assert len(manifest["invalid"]) == manifest["invalid_count"]

    for record in manifest["invalid"]:
        flow_path = REPO_ROOT / record["file"]
        result = loader.load_flow_file(flow_path, "official")
        assert not result.success, f"expected failure for {flow_path}"
        assert result.errors, f"expected loader errors for {flow_path}"
