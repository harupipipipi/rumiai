from __future__ import annotations

import json
from pathlib import Path

from core_runtime.pack_seed import write_current_pointer_atomic
from core_runtime.pack_store import active_pack_dir, active_pack_version, pack_root, version_dir


def test_pack_store_resolves_active_version_from_current_pointer(tmp_path: Path):
    managed = tmp_path / "packs"
    active = managed / "defaultspack" / "versions" / "2.5.0"
    active.mkdir(parents=True)
    (active / "ecosystem.json").write_text(
        json.dumps({"pack_id": "defaultspack", "version": "2.5.0"}),
        encoding="utf-8",
    )
    write_current_pointer_atomic("defaultspack", "2.5.0", Path("versions") / "2.5.0", managed)

    assert pack_root("defaultspack", managed) == managed / "defaultspack"
    assert version_dir("defaultspack", "2.5.0", managed) == active
    assert active_pack_dir("defaultspack", managed) == active
    assert active_pack_version("defaultspack", managed) == "2.5.0"


def test_pack_store_ignores_broken_current_pointer(tmp_path: Path):
    managed = tmp_path / "packs"
    pack = managed / "defaultspack"
    pack.mkdir(parents=True)
    (pack / "current.json").write_text(
        json.dumps(
            {
                "schema": "rumi.pack_current.v1",
                "pack_id": "defaultspack",
                "version": "2.5.0",
                "path": "../outside",
            }
        ),
        encoding="utf-8",
    )

    assert active_pack_dir("defaultspack", managed) is None
    assert active_pack_version("defaultspack", managed) == "2.5.0"
