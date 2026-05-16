from __future__ import annotations

import json
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
