"""Regressions for checked-in complete-v4 migration evidence freshness."""

from __future__ import annotations

from copy import deepcopy

from scripts.quality import scan_complete_v4_migration as scanner


def _evidence(sha: str = "parent") -> dict[str, object]:
    return {
        "schema": "io.tobkiri.quality.complete-v4-migration-evidence.v1",
        "source": {"observed_head_sha": sha, "test_file": "gate.py"},
        "counts": {"production_pack_directories": 142},
        "findings": {"legacy": []},
    }


def test_evidence_drift_accepts_exact_parent_provenance(monkeypatch) -> None:
    """An evidence commit may record its parent without self-reference."""

    monkeypatch.setattr(
        scanner.subprocess,
        "check_output",
        lambda command, **_kwargs: "head\n" if command[-1] == "HEAD" else "parent\n",
    )
    assert scanner.evidence_drift(_evidence(), _evidence("head")) == []


def test_evidence_drift_rejects_count_and_old_sha(monkeypatch) -> None:
    """A stale inventory cannot hide count drift behind an older commit SHA."""

    monkeypatch.setattr(
        scanner.subprocess,
        "check_output",
        lambda command, **_kwargs: "head\n" if command[-1] == "HEAD" else "parent\n",
    )
    tracked = _evidence("old")
    observed = deepcopy(tracked)
    observed["source"]["observed_head_sha"] = "head"  # type: ignore[index]
    observed["counts"]["production_pack_directories"] = 143  # type: ignore[index]
    assert scanner.evidence_drift(tracked, observed) == [
        "tracked evidence differs from the current semantic scan",
        "tracked observed_head_sha is stale: expected head or parent, got 'old'",
    ]
