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
