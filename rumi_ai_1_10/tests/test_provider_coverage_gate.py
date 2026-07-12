from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
QUALITY = ROOT / "scripts" / "quality"
if str(QUALITY) not in sys.path:
    sys.path.insert(0, str(QUALITY))

from check_provider_coverage import build_report, main, render_markdown  # noqa: E402


def _write(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _matrix(*provider_ids):
    return {
        "schema_version": 2,
        "generated_at": "2026-07-11",
        "providers": [
            {
                "provider_id": provider_id,
                "tier": "required",
                "completion_required": True,
            }
            for provider_id in provider_ids
        ],
    }


def test_real_matrix_report_is_deterministic_and_report_only(tmp_path):
    first = build_report()
    second = build_report()
    assert first == second
    assert first["provider_count_expected"] == 82
    assert first["passed"] is False
    assert first["failures"]["missing_providers"]
    assert main(["--json-output", str(tmp_path / "report.json")]) == 0


def test_synthetic_complete_catalog_passes(tmp_path):
    root = tmp_path / "repo"
    matrix = root / "matrix.json"
    _write(matrix, _matrix("provider-a"))
    _write(
        root / "ecosystem" / "defaultspack" / "domain" / "providers" / "provider-a" / "manifest.json",
        {
            "provider_manifest": {"id": "provider-a", "enabled": True},
            "models": [{"model_id": "org/exact:tag"}],
        },
    )
    _write(
        root / "provider_coverage" / "fixtures" / "provider-a.json",
        {"provider_id": "provider-a", "visible_ids": ["org/exact:tag"]},
    )
    report = build_report(root=root, matrix_path=matrix)
    assert report["passed"] is True
    assert report["failure_count"] == 0


def test_gate_finds_duplicates_defaults_equality_and_secret_caches(tmp_path):
    root = tmp_path / "repo"
    matrix = root / "matrix.json"
    _write(matrix, _matrix("provider-a", "provider-missing"))
    component = root / "ecosystem" / "defaultspack" / "domain" / "providers" / "provider-a" / "manifest.json"
    catalog = root / "ecosystem" / "rumi_model_catalog_pack" / "extensions" / "llm" / "providers" / "provider-a" / "manifest.json"
    _write(component, {"provider_manifest": {"id": "provider-a", "default_model": "retired"}})
    _write(catalog, {"id": "provider-a", "models": [{"model_id": "stale"}]})
    _write(root / "provider_coverage" / "fixtures" / "provider-a.json", {"visible_ids": ["current"]})
    cache = root / "cache"
    _write(cache / "models.json", {"authorization": "Bearer private-token-value"})

    report = build_report(root=root, matrix_path=matrix, cache_roots=[cache])
    failures = report["failures"]
    assert failures["missing_providers"] == ["provider-missing"]
    assert failures["duplicate_canonical_owners"][0]["provider_id"] == "provider-a"
    assert failures["invalid_defaults"][0]["default_model"] == "retired"
    assert failures["missing_authoritative_model_ids"] == [{"provider_id": "provider-a", "model_id": "current"}]
    assert failures["stale_invokable_model_ids"] == [{"provider_id": "provider-a", "model_id": "stale"}]
    assert failures["secret_bearing_caches"]


def test_required_mode_fails_and_markdown_is_stable(tmp_path):
    matrix = tmp_path / "matrix.json"
    _write(matrix, _matrix("missing"))
    gate = tmp_path / "gate.json"
    _write(gate, {"required": False})
    assert main(["--matrix", str(matrix), "--gate", str(gate)]) == 0
    assert main(["--matrix", str(matrix), "--gate", str(gate), "--required"]) == 1
    report = build_report(root=tmp_path, matrix_path=matrix)
    markdown = render_markdown(report)
    assert markdown == render_markdown(report)
    assert "REPORTING GAPS" in markdown
