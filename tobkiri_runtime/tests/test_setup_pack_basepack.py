from __future__ import annotations

from pathlib import Path

from ecosystem.setup_pack.pack_selector import PackSelector


def test_basepack_setup_profile_is_discoverable() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    selector = PackSelector(repo_root / "ecosystem")
    candidates = {candidate.pack_id: candidate for candidate in selector.scan_candidates()}

    assert "defaultspack" in candidates
    candidate = candidates["defaultspack"]
    assert candidate.target_pack_id == "defaultspack"
    assert candidate.display_name == "Tobkiri Defaults v4"
    assert candidate.risk_level == "medium"
    assert candidate.all_ok_eligible is False
    assert candidate.compatibility["target_pack_version"] == ">=4.0.0"
    assert candidate.marketplace["status"] == "verified"
    assert candidate.signing["mode"] == "repository_reviewed"
    assert candidate.install_prompt["base_pack_id"] == "defaults-basepack"
    assert candidate.install_prompt["shell_provider_id"] == "shell.tauri.default"
    assert candidate.install_prompt["profile_id"] == "defaults"
