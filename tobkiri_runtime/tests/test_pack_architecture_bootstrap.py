from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "quality" / "verify_pack_architecture_bootstrap.py"
BASELINE = ROOT / "scripts" / "quality" / "pack_architecture_baseline.json"
WORKFLOW = ROOT / ".github" / "workflows" / "test.yml"
BOOTSTRAP_COMMIT = "49df7570167176fba71420b2d9131d082eb696d3"
BOOTSTRAP_BLOB = "72c0b006778b24a6459115bf569890fcf3636f35"


def _verifier():
    spec = importlib.util.spec_from_file_location(
        "pack_architecture_bootstrap_test", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write(document: dict[str, object], path: Path) -> None:
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def test_reviewed_bootstrap_reference_accepts_only_exact_candidate(
    tmp_path: Path,
) -> None:
    verifier = _verifier()
    reference = tmp_path / "reference.json"
    candidate = tmp_path / "candidate.json"
    reference.write_bytes(BASELINE.read_bytes())
    candidate.write_bytes(BASELINE.read_bytes())

    verifier.verify_bootstrap(candidate, reference)


@pytest.mark.parametrize("drift", ("extra", "missing", "modified"))
def test_reviewed_bootstrap_reference_rejects_candidate_drift(
    tmp_path: Path, drift: str
) -> None:
    verifier = _verifier()
    reference = tmp_path / "reference.json"
    candidate = tmp_path / "candidate.json"
    reference.write_bytes(BASELINE.read_bytes())
    document = json.loads(BASELINE.read_text(encoding="utf-8"))
    if drift == "extra":
        extra = dict(document["exceptions"][0])
        extra["identity"] += "-extra"
        document["exceptions"].append(extra)
    elif drift == "missing":
        document["exceptions"].pop()
    else:
        document["exceptions"][0]["reason"] = "candidate-authored reason"
    _write(document, candidate)

    with pytest.raises(ValueError):
        verifier.verify_bootstrap(candidate, reference)


def test_candidate_cannot_be_its_own_bootstrap_reference() -> None:
    with pytest.raises(ValueError, match="cannot authorize its own"):
        _verifier().verify_bootstrap(BASELINE, BASELINE)


def test_workflow_uses_content_addressed_bootstrap_reference() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert f"bootstrap_commit='{BOOTSTRAP_COMMIT}'" in workflow
    assert f"bootstrap_blob='{BOOTSTRAP_BLOB}'" in workflow
    assert "verify_pack_architecture_bootstrap.py" in workflow
    assert 'git show "${bootstrap_commit}:${baseline}" > "${reference}"' in workflow
    assert 'cp scripts/quality/pack_architecture_baseline.json "${reference}"' not in workflow
