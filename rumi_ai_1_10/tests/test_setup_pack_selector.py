from __future__ import annotations

import json
from pathlib import Path

from ecosystem.setup_pack.pack_selector import PackSelector


def test_scan_and_grant(tmp_path):
    ecosystem = tmp_path / "eco"
    setup_pack_root = ecosystem / "setup_pack"
    setup_pack_root.mkdir(parents=True)
    pack = setup_pack_root / "defaultspack"
    pack.mkdir()
    (pack / "pack.json").write_text(
        json.dumps(
            {
                "pack_id": "defaultspack",
                "target_pack_id": "defaultspack",
                "supports_all_ok": True,
            }
        ),
        encoding="utf-8",
    )
    target = ecosystem / "defaultspack"
    target.mkdir()
    (target / "ecosystem.json").write_text(
        json.dumps({"pack_identity": "rumi.defaults"}),
        encoding="utf-8",
    )
    selector = PackSelector(setup_pack_root)
    candidates = selector.scan_candidates()
    assert len(candidates) == 1
    assert candidates[0].target_pack_id == "defaultspack"
    assert candidates[0].pack_identity == "rumi.defaults"
    assert candidates[0].all_ok_eligible
    assert selector.select_and_grant("defaultspack")["granted"]


def test_validate_candidates_checks_dependencies_platform_python_and_signing(tmp_path):
    ecosystem = tmp_path / "eco"
    setup_pack_root = ecosystem / "setup_pack"
    setup_pack_root.mkdir(parents=True)
    pack = setup_pack_root / "agentpack"
    pack.mkdir()
    (pack / "pack.json").write_text(
        json.dumps(
            {
                "pack_id": "agentpack",
                "depends_on": [{"pack_id": "defaultspack", "version": ">=2.0.0"}],
                "compatibility": {
                    "platforms": ["windows"],
                    "python": ">=3.11,<3.13",
                },
                "marketplace": {"channel": "beta"},
                "signing": {"required": True},
            }
        ),
        encoding="utf-8",
    )

    issues = PackSelector(setup_pack_root).validate_candidates(
        installed_packs={"defaultspack": {"version": "1.9.0"}},
        platform_name="linux",
        python_version="3.10.9",
    )

    issue_types = {issue["type"] for issue in issues}
    assert {
        "version_mismatch",
        "unsupported_platform",
        "python_version_mismatch",
        "unsigned_pack",
        "invalid_marketplace_metadata",
    } <= issue_types


def test_validate_candidates_accepts_compatible_signed_pack(tmp_path):
    ecosystem = tmp_path / "eco"
    setup_pack_root = ecosystem / "setup_pack"
    setup_pack_root.mkdir(parents=True)
    pack = setup_pack_root / "agentpack"
    pack.mkdir()
    (pack / "pack.json").write_text(
        json.dumps(
            {
                "pack_id": "agentpack",
                "dependencies": {"defaultspack": {"version": ">=1.0.0"}},
                "platforms": ["windows"],
                "python_requires": ">=3.10",
                "marketplace": {"id": "rumi.agentpack"},
                "signing": {"algorithm": "ed25519", "signature": "abc123"},
            }
        ),
        encoding="utf-8",
    )

    issues = PackSelector(setup_pack_root).validate_candidates(
        installed_packs={"defaultspack": {"version": "1.2.0"}},
        platform_name="win32",
        python_version="3.11.1",
        require_signed=True,
    )

    assert issues == []


def test_scan_candidates_exposes_conflict_and_promotion_metadata(tmp_path):
    ecosystem = tmp_path / "eco"
    setup_pack_root = ecosystem / "setup_pack"
    setup_pack_root.mkdir(parents=True)
    pack = setup_pack_root / "workspace"
    pack.mkdir()
    (pack / "pack.json").write_text(
        json.dumps(
            {
                "pack_id": "workspace",
                "conflicts_with": [
                    {
                        "pack_id": "legacy_workspace",
                        "reason": "Both own generated office artifacts.",
                        "resolution": "prefer_workspace",
                    }
                ],
                "overlap_policy": {"tool_aliases": "prefer_explicit_pack_namespace"},
                "defaultspack_promotion": {"eligible": True},
            }
        ),
        encoding="utf-8",
    )

    candidate = PackSelector(setup_pack_root).scan_candidates()[0]

    assert candidate.conflicts_with[0]["pack_id"] == "legacy_workspace"
    assert candidate.overlap_policy["tool_aliases"] == "prefer_explicit_pack_namespace"
    assert candidate.defaultspack_promotion["eligible"] is True
    assert candidate.to_dict()["conflicts_with"][0]["resolution"] == "prefer_workspace"


def test_validate_candidates_reports_installed_pack_conflict(tmp_path):
    ecosystem = tmp_path / "eco"
    setup_pack_root = ecosystem / "setup_pack"
    setup_pack_root.mkdir(parents=True)
    pack = setup_pack_root / "workspace"
    pack.mkdir()
    (pack / "pack.json").write_text(
        json.dumps(
            {
                "pack_id": "workspace",
                "conflicts_with": [
                    {
                        "pack_id": "legacy_workspace",
                        "reason": "Both own generated office artifacts.",
                        "resolution": "prefer_workspace",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    issues = PackSelector(setup_pack_root).validate_candidates(
        installed_packs={"legacy_workspace": {"version": "1.0.0"}},
    )

    assert issues == [
        {
            "type": "pack_conflict",
            "pack_id": "workspace",
            "conflicts_with": "legacy_workspace",
            "resolution": "prefer_workspace",
            "reason": "Both own generated office artifacts.",
            "severity": "error",
        }
    ]


def test_bundled_setup_pack_metadata_validates_cleanly():
    repo_root = Path(__file__).resolve().parent.parent
    selector = PackSelector(repo_root / "ecosystem")

    issues = selector.validate_candidates(platform_name="darwin", python_version="3.11.0")

    assert issues == []


def test_validate_candidates_rejects_invalid_conflict_metadata(tmp_path):
    ecosystem = tmp_path / "eco"
    setup_pack_root = ecosystem / "setup_pack"
    setup_pack_root.mkdir(parents=True)
    pack = setup_pack_root / "workspace"
    pack.mkdir()
    (pack / "pack.json").write_text(
        json.dumps(
            {
                "pack_id": "workspace",
                "target_pack_id": "workspace",
                "conflicts_with": [
                    {
                        "reason": "Missing the conflicting pack id.",
                        "resolution": "choose_one_pack",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    issues = PackSelector(setup_pack_root).validate_candidates()

    assert issues == [
        {
            "type": "invalid_setup_pack_metadata",
            "pack_id": "workspace",
            "severity": "error",
            "reason": "invalid_setup_pack_schema",
            "message": "setup-pack field 'conflicts_with[0].pack_id' is required",
            "field": "conflicts_with[0]",
        }
    ]


def test_validate_candidates_accepts_bundled_marketplace_and_signing_metadata(tmp_path):
    ecosystem = tmp_path / "eco"
    setup_pack_root = ecosystem / "setup_pack"
    setup_pack_root.mkdir(parents=True)
    pack = setup_pack_root / "defaultspack"
    pack.mkdir()
    (pack / "pack.json").write_text(
        json.dumps(
            {
                "pack_id": "defaultspack",
                "target_pack_id": "defaultspack",
                "marketplace": {
                    "registry": "bundled",
                    "publisher": "rumi-ai",
                    "status": "verified",
                },
                "signing": {
                    "mode": "repository_reviewed",
                    "verified": True,
                },
            }
        ),
        encoding="utf-8",
    )

    issues = PackSelector(setup_pack_root).validate_candidates(
        platform_name="darwin",
        python_version="3.11.0",
    )

    assert issues == []


def test_validate_candidates_ignores_conflict_candidates_that_are_not_installed(tmp_path):
    ecosystem = tmp_path / "eco"
    setup_pack_root = ecosystem / "setup_pack"
    setup_pack_root.mkdir(parents=True)

    workspace = setup_pack_root / "workspace"
    workspace.mkdir()
    (workspace / "pack.json").write_text(
        json.dumps(
            {
                "pack_id": "workspace",
                "conflicts_with": [
                    {
                        "pack_id": "legacy_workspace",
                        "reason": "Both own generated office artifacts.",
                        "resolution": "prefer_workspace",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    legacy = setup_pack_root / "legacy_workspace"
    legacy.mkdir()
    (legacy / "pack.json").write_text(json.dumps({"pack_id": "legacy_workspace"}), encoding="utf-8")

    issues = PackSelector(setup_pack_root).validate_candidates(installed_packs={})

    assert issues == []
