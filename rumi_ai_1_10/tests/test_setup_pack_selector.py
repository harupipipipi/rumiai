from __future__ import annotations

import json
from ecosystem.setup_pack.pack_selector import PackSelector, DEFAULTSPACK_IDENTITY


def test_scan_and_grant(tmp_path):
    ecosystem = tmp_path / "eco"
    ecosystem.mkdir()
    pack = ecosystem / "defaultspack"
    pack.mkdir()
    (pack / "ecosystem.json").write_text(
        json.dumps({"pack_id": "defaultspack", "pack_identity": DEFAULTSPACK_IDENTITY}),
        encoding="utf-8",
    )
    selector = PackSelector(ecosystem)
    candidates = selector.scan_candidates()
    assert len(candidates) == 1
    assert candidates[0].all_ok_eligible
    assert selector.select_and_grant("defaultspack")["granted"]
