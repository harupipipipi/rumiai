from __future__ import annotations

import json
from pathlib import Path

from core_runtime import paths
from core_runtime.pack_seed import write_current_pointer_atomic


def _pack(root: Path, pack_id: str, version: str) -> Path:
    pack_dir = root / pack_id
    pack_dir.mkdir(parents=True, exist_ok=True)
    (pack_dir / "ecosystem.json").write_text(
        json.dumps({"pack_id": pack_id, "pack_identity": f"local:{pack_id}", "version": version}),
        encoding="utf-8",
    )
    return pack_dir


def test_managed_current_wins_over_bundled_seed_and_legacy(tmp_path, monkeypatch):
    managed = tmp_path / "user_data" / "packs"
    seeds = tmp_path / "pack_seeds"
    ecosystem = tmp_path / "ecosystem"
    active = _pack(managed / "defaultspack" / "versions", "2.5.0", "2.5.0")
    active_manifest = json.loads((active / "ecosystem.json").read_text(encoding="utf-8"))
    active_manifest["pack_id"] = "defaultspack"
    (active / "ecosystem.json").write_text(json.dumps(active_manifest), encoding="utf-8")
    write_current_pointer_atomic("defaultspack", "2.5.0", Path("versions") / "2.5.0", managed)
    _pack(seeds, "defaultspack", "2.0.0")
    _pack(ecosystem, "defaultspack", "1.0.0")
    monkeypatch.setattr(paths, "MANAGED_PACKS_DIR", managed)
    monkeypatch.setattr(paths, "PACK_SEEDS_DIR", seeds)

    locations = {loc.pack_id: loc for loc in paths.discover_pack_locations(str(ecosystem))}

    assert locations["defaultspack"].source == "managed"
    assert locations["defaultspack"].version == "2.5.0"
    assert locations["defaultspack"].mutable is True
    assert locations["defaultspack"].ecosystem_json_path == active / "ecosystem.json"


def test_bundled_defaultspack_is_fallback_only(tmp_path, monkeypatch):
    managed = tmp_path / "user_data" / "packs"
    seeds = tmp_path / "pack_seeds"
    ecosystem = tmp_path / "ecosystem"
    _pack(ecosystem, "defaultspack", "1.0.0")
    monkeypatch.setattr(paths, "MANAGED_PACKS_DIR", managed)
    monkeypatch.setattr(paths, "PACK_SEEDS_DIR", seeds)

    locations = {loc.pack_id: loc for loc in paths.discover_pack_locations(str(ecosystem))}

    assert locations["defaultspack"].source == "bundled_legacy"
    assert locations["defaultspack"].mutable is False


def test_pack_id_mismatch_rejected(tmp_path, monkeypatch):
    managed = tmp_path / "user_data" / "packs"
    seeds = tmp_path / "pack_seeds"
    ecosystem = tmp_path / "ecosystem"
    bad = _pack(managed / "defaultspack" / "versions", "2.5.0", "2.5.0")
    data = json.loads((bad / "ecosystem.json").read_text(encoding="utf-8"))
    data["pack_id"] = "other"
    (bad / "ecosystem.json").write_text(json.dumps(data), encoding="utf-8")
    write_current_pointer_atomic("defaultspack", "2.5.0", Path("versions") / "2.5.0", managed)
    _pack(ecosystem, "defaultspack", "1.0.0")
    monkeypatch.setattr(paths, "MANAGED_PACKS_DIR", managed)
    monkeypatch.setattr(paths, "PACK_SEEDS_DIR", seeds)

    locations = {loc.pack_id: loc for loc in paths.discover_pack_locations(str(ecosystem))}

    assert locations["defaultspack"].source == "bundled_legacy"
