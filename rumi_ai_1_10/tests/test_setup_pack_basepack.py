from __future__ import annotations

from pathlib import Path

from ecosystem.setup_pack.pack_selector import PackSelector


def test_basepack_setup_profile_is_discoverable() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    selector = PackSelector(repo_root / "ecosystem")
    candidates = {candidate.pack_id: candidate for candidate in selector.scan_candidates()}

    assert "basepack" in candidates
    candidate = candidates["basepack"]
    assert candidate.target_pack_id == "defaultspack"
    assert candidate.display_name == "Basepack"
    assert candidate.risk_level == "low"
    assert candidate.all_ok_eligible is True
    assert candidate.compatibility["target_pack_version"] == ">=2.0.0"
    assert candidate.marketplace["status"] == "verified"
    assert candidate.signing["mode"] == "repository_reviewed"
