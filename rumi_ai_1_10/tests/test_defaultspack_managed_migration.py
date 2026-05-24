from __future__ import annotations

import json

from core_runtime import pack_seed, paths


def test_defaultspack_runtime_location_is_managed_after_seed_migration(tmp_path, monkeypatch):
    legacy = tmp_path / "runtime" / "ecosystem" / "defaultspack"
    legacy.mkdir(parents=True)
    (legacy / "ecosystem.json").write_text(
        json.dumps({"pack_id": "defaultspack", "pack_identity": "local:defaultspack", "version": "2.0.0"}),
        encoding="utf-8",
    )
    managed = tmp_path / "user_data" / "packs"
    monkeypatch.setattr(pack_seed, "PACK_SEEDS_DIR", tmp_path / "runtime" / "pack_seeds")
    monkeypatch.setattr(pack_seed, "BUNDLED_LEGACY_ECOSYSTEM_DIR", tmp_path / "runtime" / "ecosystem")
    monkeypatch.setattr(pack_seed, "MANAGED_PACKS_DIR", managed)
    monkeypatch.setattr(paths, "MANAGED_PACKS_DIR", managed)
    monkeypatch.setattr(paths, "PACK_SEEDS_DIR", tmp_path / "runtime" / "pack_seeds")

    pack_seed.ensure_managed_defaultspack_installed()
    loc = {item.pack_id: item for item in paths.discover_pack_locations(str(tmp_path / "runtime" / "ecosystem"))}["defaultspack"]

    assert loc.source == "managed"
    assert loc.mutable is True
    assert managed in loc.pack_dir.parents
    assert loc.pack_dir != legacy
    assert (legacy / "ecosystem.json").is_file()
