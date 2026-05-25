from __future__ import annotations

import json
from pathlib import Path

from core_runtime import pack_seed


def _write_pack(root: Path, pack_id: str = "defaultspack", version: str = "2.5.0") -> Path:
    pack_dir = root / pack_id
    pack_dir.mkdir(parents=True)
    (pack_dir / "rumi-pack.json").write_text(
        json.dumps({"schema": "rumi.pack.v1", "pack_id": pack_id, "version": version}),
        encoding="utf-8",
    )
    (pack_dir / "ecosystem.json").write_text(
        json.dumps({"pack_id": pack_id, "pack_identity": f"local:{pack_id}", "version": version}),
        encoding="utf-8",
    )
    (pack_dir / "state").mkdir()
    (pack_dir / "state" / "seed-state.json").write_text("{}", encoding="utf-8")
    return pack_dir


def test_missing_managed_defaultspack_gets_seeded(tmp_path, monkeypatch):
    seed_root = tmp_path / "pack_seeds"
    managed = tmp_path / "user_data" / "packs"
    _write_pack(seed_root)
    monkeypatch.setattr(pack_seed, "PACK_SEEDS_DIR", seed_root)
    monkeypatch.setattr(pack_seed, "MANAGED_PACKS_DIR", managed)
    monkeypatch.setattr(pack_seed, "BUNDLED_LEGACY_ECOSYSTEM_DIR", tmp_path / "ecosystem")

    result = pack_seed.ensure_managed_defaultspack_installed()

    assert result["installed"] is True
    current = json.loads((managed / "defaultspack" / "current.json").read_text(encoding="utf-8"))
    assert current["path"] == "versions/2.5.0"
    assert (managed / "defaultspack" / "versions" / "2.5.0" / "ecosystem.json").is_file()
    assert not (managed / "defaultspack" / "versions" / "2.5.0" / "state").exists()


def test_existing_valid_current_pointer_without_seed_record_is_not_overwritten(tmp_path, monkeypatch):
    seed_root = tmp_path / "pack_seeds"
    managed = tmp_path / "user_data" / "packs"
    _write_pack(seed_root, version="9.9.9")
    target = managed / "defaultspack" / "versions" / "1.0.0"
    target.mkdir(parents=True)
    (target / "ecosystem.json").write_text(
        json.dumps({"pack_id": "defaultspack", "pack_identity": "local:defaultspack", "version": "1.0.0"}),
        encoding="utf-8",
    )
    pack_seed.write_current_pointer_atomic("defaultspack", "1.0.0", Path("versions") / "1.0.0", managed)
    monkeypatch.setattr(pack_seed, "PACK_SEEDS_DIR", seed_root)
    monkeypatch.setattr(pack_seed, "MANAGED_PACKS_DIR", managed)

    result = pack_seed.ensure_managed_defaultspack_installed()

    assert result["installed"] is False
    current = json.loads((managed / "defaultspack" / "current.json").read_text(encoding="utf-8"))
    assert current["version"] == "1.0.0"


def test_existing_manual_current_pointer_is_not_overwritten_by_newer_seed(tmp_path, monkeypatch):
    seed_root = tmp_path / "pack_seeds"
    managed = tmp_path / "user_data" / "packs"
    _write_pack(seed_root, version="9.9.9")
    target = managed / "defaultspack" / "versions" / "1.0.0"
    target.mkdir(parents=True)
    (target / "ecosystem.json").write_text(
        json.dumps({"pack_id": "defaultspack", "pack_identity": "local:defaultspack", "version": "1.0.0"}),
        encoding="utf-8",
    )
    pack_seed.write_current_pointer_atomic("defaultspack", "1.0.0", Path("versions") / "1.0.0", managed)
    (managed / "defaultspack" / "install_record.json").write_text(
        json.dumps({"schema": "rumi.pack_install_record.v1", "pack_id": "defaultspack", "version": "1.0.0", "source": "rumi-pack"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(pack_seed, "PACK_SEEDS_DIR", seed_root)
    monkeypatch.setattr(pack_seed, "MANAGED_PACKS_DIR", managed)

    result = pack_seed.ensure_managed_defaultspack_installed()

    assert result["installed"] is False
    current = json.loads((managed / "defaultspack" / "current.json").read_text(encoding="utf-8"))
    assert current["version"] == "1.0.0"


def test_seed_managed_current_upgrades_to_newer_bundled_seed(tmp_path, monkeypatch):
    seed_root = tmp_path / "pack_seeds"
    managed = tmp_path / "user_data" / "packs"
    _write_pack(seed_root, version="9.9.9")
    target = managed / "defaultspack" / "versions" / "1.0.0"
    target.mkdir(parents=True)
    (target / "ecosystem.json").write_text(
        json.dumps({"pack_id": "defaultspack", "pack_identity": "local:defaultspack", "version": "1.0.0"}),
        encoding="utf-8",
    )
    pack_state = managed / "defaultspack" / "state"
    pack_state.mkdir(parents=True)
    (pack_state / "user.json").write_text("{}", encoding="utf-8")
    pack_seed.write_current_pointer_atomic("defaultspack", "1.0.0", Path("versions") / "1.0.0", managed)
    (managed / "defaultspack" / "install_record.json").write_text(
        json.dumps({"schema": "rumi.pack_install_record.v1", "pack_id": "defaultspack", "version": "1.0.0", "source": "seed"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(pack_seed, "PACK_SEEDS_DIR", seed_root)
    monkeypatch.setattr(pack_seed, "MANAGED_PACKS_DIR", managed)

    result = pack_seed.ensure_managed_defaultspack_installed()

    assert result["installed"] is True
    assert result["version"] == "9.9.9"
    current = json.loads((managed / "defaultspack" / "current.json").read_text(encoding="utf-8"))
    assert current["version"] == "9.9.9"
    assert (managed / "defaultspack" / "versions" / "9.9.9" / "ecosystem.json").is_file()
    assert (pack_state / "user.json").is_file()


def test_legacy_seed_migration_current_upgrades_to_newer_bundled_seed(tmp_path, monkeypatch):
    seed_root = tmp_path / "pack_seeds"
    managed = tmp_path / "user_data" / "packs"
    _write_pack(seed_root, version="2.5.0")
    target = managed / "defaultspack" / "versions" / "2.0.0"
    target.mkdir(parents=True)
    (target / "ecosystem.json").write_text(
        json.dumps({"pack_id": "defaultspack", "pack_identity": "local:defaultspack", "version": "2.0.0"}),
        encoding="utf-8",
    )
    pack_seed.write_current_pointer_atomic("defaultspack", "2.0.0", Path("versions") / "2.0.0", managed)
    (managed / "defaultspack" / "install_record.json").write_text(
        json.dumps({"schema": "rumi.pack_install_record.v1", "pack_id": "defaultspack", "version": "2.0.0", "source": "legacy_seed_migration"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(pack_seed, "PACK_SEEDS_DIR", seed_root)
    monkeypatch.setattr(pack_seed, "MANAGED_PACKS_DIR", managed)

    result = pack_seed.ensure_managed_defaultspack_installed()

    assert result["installed"] is True
    assert result["version"] == "2.5.0"
    current = json.loads((managed / "defaultspack" / "current.json").read_text(encoding="utf-8"))
    assert current["version"] == "2.5.0"


def test_legacy_seed_migration_copies_bundled_defaultspack(tmp_path, monkeypatch):
    legacy_root = tmp_path / "ecosystem"
    managed = tmp_path / "user_data" / "packs"
    _write_pack(legacy_root, version="2.0.0")
    monkeypatch.setattr(pack_seed, "PACK_SEEDS_DIR", tmp_path / "missing_seeds")
    monkeypatch.setattr(pack_seed, "BUNDLED_LEGACY_ECOSYSTEM_DIR", legacy_root)
    monkeypatch.setattr(pack_seed, "MANAGED_PACKS_DIR", managed)

    result = pack_seed.ensure_seed_pack_installed("defaultspack")

    assert result["source"] == "legacy_seed_migration"
    assert (managed / "defaultspack" / "versions" / "2.0.0" / "ecosystem.json").is_file()


def test_official_seed_packs_include_default_tools_pack(tmp_path, monkeypatch):
    seed_root = tmp_path / "pack_seeds"
    managed = tmp_path / "user_data" / "packs"
    _write_pack(seed_root, pack_id="defaultspack", version="2.0.0")
    _write_pack(seed_root, pack_id="rumi_default_tools_pack", version="1.0.0")
    monkeypatch.setattr(pack_seed, "PACK_SEEDS_DIR", seed_root)
    monkeypatch.setattr(pack_seed, "MANAGED_PACKS_DIR", managed)
    monkeypatch.setattr(pack_seed, "BUNDLED_LEGACY_ECOSYSTEM_DIR", tmp_path / "ecosystem")

    results = pack_seed.ensure_official_seed_packs_installed()

    assert {item["pack_id"] for item in results} == {"defaultspack", "rumi_default_tools_pack"}
    assert (managed / "defaultspack" / "current.json").is_file()
    assert (managed / "rumi_default_tools_pack" / "current.json").is_file()
