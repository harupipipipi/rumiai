from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from core_runtime.pack_seed import write_current_pointer_atomic
from core_runtime.update.download import sha256_file
from core_runtime.update.pack_update_manager import PackUpdateError, PackUpdateManager
from core_runtime.update.trust import sign_hmac


def _manager_for_bundle(tmp_path: Path, managed: Path, bundle: Path, *, signature: str | None = None, sha: str | None = None, min_core: str = "1.10.0") -> PackUpdateManager:
    digest = sha or sha256_file(bundle)
    payload = {
        "schema": "rumi.pack_index.v1",
        "generated_at": "2026-05-24T00:00:00Z",
        "channel": "stable",
        "packs": {
            "defaultspack": {
                "latest": "2.5.0",
                "versions": {
                    "2.5.0": {
                        "url": f"file://{bundle}",
                        "sha256": digest,
                        "signature": signature if signature is not None else sign_hmac(digest, "test", "secret"),
                        "min_core_version": min_core,
                        "max_core_version": "<2.0.0",
                    }
                },
            }
        },
    }
    index = tmp_path / "index.json"
    index.write_text(json.dumps(payload), encoding="utf-8")
    return PackUpdateManager(
        managed_dir=managed,
        pack_state_dir=tmp_path / "pack_state",
        index_url=f"file://{index}",
        trust_roots_path=_trust(tmp_path),
        core_version="1.10.0",
    )


def _write_pack_dir(root: Path, pack_id: str = "defaultspack", version: str = "2.5.0") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "rumi-pack.json").write_text(
        json.dumps(
            {
                "schema": "rumi.pack.v1",
                "pack_id": pack_id,
                "version": version,
                "channel": "stable",
                "compatibility": {"min_core_version": "1.10.0", "max_core_version": "<2.0.0", "min_viewer_version": "0.1.0"},
                "entrypoints": {"ecosystem": "ecosystem.json"},
                "protected_paths": ["user_data/**", "state/**", "secrets/**", ".env", "*.local.*"],
                "requires": {"kernel_restart": False, "routes_reload": True},
            }
        ),
        encoding="utf-8",
    )
    (root / "ecosystem.json").write_text(
        json.dumps({"pack_id": pack_id, "pack_identity": f"local:{pack_id}", "version": version}),
        encoding="utf-8",
    )
    (root / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    return root


def _bundle_from_dir(pack_dir: Path, bundle: Path) -> Path:
    files = [p for p in sorted(pack_dir.rglob("*")) if p.is_file()]
    manifest = {p.relative_to(pack_dir).as_posix(): sha256_file(p) for p in files}
    with zipfile.ZipFile(bundle, "w") as zf:
        for path in files:
            zf.write(path, path.relative_to(pack_dir).as_posix())
        zf.writestr("manifest.json", json.dumps({"schema": "rumi.pack_manifest.v1", "files": manifest}))
    return bundle


def _trust(tmp_path: Path) -> Path:
    path = tmp_path / "trust_roots.json"
    path.write_text(json.dumps({"schema": "rumi.trust_roots.v1", "hmac_keys": {"test": "secret"}}), encoding="utf-8")
    return path


def _set_current(managed: Path) -> None:
    _write_pack_dir(managed / "defaultspack" / "versions" / "2.4.1", version="2.4.1")
    write_current_pointer_atomic("defaultspack", "2.4.1", Path("versions") / "2.4.1", managed)


def _current_version(managed: Path) -> str:
    return json.loads((managed / "defaultspack" / "current.json").read_text(encoding="utf-8"))["version"]


def test_sha256_mismatch_rejected_and_current_unchanged(tmp_path):
    managed = tmp_path / "packs"
    _set_current(managed)
    bundle = _bundle_from_dir(_write_pack_dir(tmp_path / "src"), tmp_path / "pack.rumi-pack")
    manager = _manager_for_bundle(tmp_path, managed, bundle, sha="0" * 64)

    with pytest.raises(Exception):
        manager.apply_pack("defaultspack")

    assert _current_version(managed) == "2.4.1"


def test_signature_mismatch_rejected_and_current_unchanged(tmp_path):
    managed = tmp_path / "packs"
    _set_current(managed)
    bundle = _bundle_from_dir(_write_pack_dir(tmp_path / "src"), tmp_path / "pack.rumi-pack")
    manager = _manager_for_bundle(tmp_path, managed, bundle, signature="hmac-sha256:test:bad")

    with pytest.raises(Exception):
        manager.apply_pack("defaultspack")

    assert _current_version(managed) == "2.4.1"


def test_pack_id_mismatch_rejected(tmp_path):
    managed = tmp_path / "packs"
    _set_current(managed)
    source = _write_pack_dir(tmp_path / "src", pack_id="other")
    bundle = _bundle_from_dir(source, tmp_path / "pack.rumi-pack")
    manager = _manager_for_bundle(tmp_path, managed, bundle)

    with pytest.raises(Exception):
        manager.apply_pack("defaultspack")

    assert _current_version(managed) == "2.4.1"


def test_path_traversal_rejected(tmp_path):
    managed = tmp_path / "packs"
    _set_current(managed)
    bundle = tmp_path / "traversal.rumi-pack"
    with zipfile.ZipFile(bundle, "w") as zf:
        zf.writestr("../evil.txt", "x")
    manager = _manager_for_bundle(tmp_path, managed, bundle)

    with pytest.raises(Exception):
        manager.apply_pack("defaultspack")

    assert _current_version(managed) == "2.4.1"


def test_symlink_rejected(tmp_path):
    managed = tmp_path / "packs"
    _set_current(managed)
    source = _write_pack_dir(tmp_path / "src")
    bundle = _bundle_from_dir(source, tmp_path / "symlink.rumi-pack")
    with zipfile.ZipFile(bundle, "a") as zf:
        info = zipfile.ZipInfo("link")
        info.external_attr = (0o120777 << 16)
        zf.writestr(info, "target")
    manager = _manager_for_bundle(tmp_path, managed, bundle, sha=sha256_file(bundle))

    with pytest.raises(Exception):
        manager.apply_pack("defaultspack")

    assert _current_version(managed) == "2.4.1"


def test_top_level_protected_path_rejected(tmp_path):
    managed = tmp_path / "packs"
    _set_current(managed)
    source = _write_pack_dir(tmp_path / "src")
    (source / "state").write_text("do not install", encoding="utf-8")
    bundle = _bundle_from_dir(source, tmp_path / "protected.rumi-pack")
    manager = _manager_for_bundle(tmp_path, managed, bundle)

    with pytest.raises(Exception):
        manager.apply_pack("defaultspack")

    assert _current_version(managed) == "2.4.1"


def test_incompatible_core_version_rejected(tmp_path):
    managed = tmp_path / "packs"
    _set_current(managed)
    bundle = _bundle_from_dir(_write_pack_dir(tmp_path / "src"), tmp_path / "pack.rumi-pack")
    manager = _manager_for_bundle(tmp_path, managed, bundle, min_core="9.0.0")

    with pytest.raises(Exception):
        manager.apply_pack("defaultspack")

    assert _current_version(managed) == "2.4.1"


def test_unsafe_pack_id_rejected_before_staging_paths_are_created(tmp_path):
    managed = tmp_path / "packs"
    manager = PackUpdateManager(managed_dir=managed, pack_state_dir=tmp_path / "pack_state")

    with pytest.raises(PackUpdateError):
        manager.stage_pack("../../escape_probe")

    assert not (tmp_path / "escape_probe").exists()
    assert not (tmp_path / ".update.lock").exists()


def test_unsafe_pack_id_from_index_does_not_create_managed_paths(tmp_path):
    managed = tmp_path / "packs"
    index = tmp_path / "index.json"
    index.write_text(
        json.dumps(
            {
                "schema": "rumi.pack_index.v1",
                "generated_at": "2026-05-24T00:00:00Z",
                "channel": "stable",
                "packs": {"../../escape_probe": {"latest": "1.0.0", "versions": {}}},
            }
        ),
        encoding="utf-8",
    )
    manager = PackUpdateManager(
        managed_dir=managed,
        pack_state_dir=tmp_path / "pack_state",
        index_url=f"file://{index}",
    )

    checks = manager.check_all()

    assert checks[0].target == "pack:invalid"
    assert checks[0].errors
    assert not (tmp_path / "escape_probe").exists()
