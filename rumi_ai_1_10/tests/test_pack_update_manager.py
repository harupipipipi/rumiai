from __future__ import annotations

import base64
import json
import zipfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core_runtime.update.download import sha256_file
from core_runtime.update.pack_update_manager import PackUpdateManager
from core_runtime.update.models import PackUpdateCheck, PackUpdateResult
from core_runtime.update.trust import (
    index_signature_payload,
    pack_bundle_signature_payload,
    public_key_to_b64,
    sign_ed25519,
    signature_entry,
)


def _signing_key() -> tuple[str, str, str]:
    private_key = Ed25519PrivateKey.generate()
    private_raw = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return "test", base64.b64encode(private_raw).decode("ascii"), public_key_to_b64(private_key.public_key())


_TEST_KEY_ID, _TEST_PRIVATE_KEY, _TEST_PUBLIC_KEY = _signing_key()


@pytest.fixture(autouse=True)
def _official_update_trust_root(tmp_path, monkeypatch):
    path = tmp_path / "official_trust_roots.json"
    path.write_text(
        json.dumps({"schema": "rumi.trust_roots.v1", "ed25519_public_keys": {_TEST_KEY_ID: _TEST_PUBLIC_KEY}}),
        encoding="utf-8",
    )
    monkeypatch.setattr("core_runtime.update.trust.OFFICIAL_TRUST_ROOTS_PATH", path)


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


def _index(tmp_path: Path, bundle: Path, version: str = "2.5.0", signature: str | None = None) -> Path:
    digest = sha256_file(bundle)
    payload = {
        "schema": "rumi.pack_index.v1",
        "generated_at": "2026-05-24T00:00:00Z",
        "channel": "stable",
        "packs": {
            "defaultspack": {
                "latest": version,
                "versions": {
                    version: {
                        "url": f"file://{bundle}",
                        "sha256": digest,
                        "signature": signature or sign_ed25519(
                            pack_bundle_signature_payload(digest),
                            _TEST_KEY_ID,
                            _TEST_PRIVATE_KEY,
                        ),
                        "signature_scheme": "ed25519",
                        "key_id": _TEST_KEY_ID,
                        "min_core_version": "1.10.0",
                        "max_core_version": "<2.0.0",
                    }
                },
            }
        },
    }
    payload["signatures"] = [
        signature_entry(sign_ed25519(index_signature_payload(payload), _TEST_KEY_ID, _TEST_PRIVATE_KEY))
    ]
    path = tmp_path / "pack-index.stable.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _trust(tmp_path: Path) -> Path:
    path = tmp_path / "trust_roots.json"
    path.write_text(
        json.dumps({"schema": "rumi.trust_roots.v1", "ed25519_public_keys": {_TEST_KEY_ID: _TEST_PUBLIC_KEY}}),
        encoding="utf-8",
    )
    return path


def test_defaultspack_update_writes_managed_versions_and_preserves_state(tmp_path):
    managed = tmp_path / "user_data" / "packs"
    old = _write_pack_dir(managed / "defaultspack" / "versions" / "2.4.1", version="2.4.1")
    (managed / "defaultspack" / "state").mkdir(parents=True)
    (managed / "defaultspack" / "state" / "chat.json").write_text("keep", encoding="utf-8")
    from core_runtime.pack_seed import write_current_pointer_atomic

    write_current_pointer_atomic("defaultspack", "2.4.1", Path("versions") / "2.4.1", managed)
    source = _write_pack_dir(tmp_path / "src", version="2.5.0")
    bundle = _bundle_from_dir(source, tmp_path / "defaultspack-2.5.0.rumi-pack")
    manager = PackUpdateManager(
        managed_dir=managed,
        pack_state_dir=tmp_path / "pack_state",
        index_url=f"file://{_index(tmp_path, bundle)}",
        trust_roots_path=_trust(tmp_path),
    )

    result = manager.apply_pack("defaultspack")

    assert result.applied is True
    assert (managed / "defaultspack" / "versions" / "2.5.0" / "module.py").is_file()
    assert (managed / "defaultspack" / "state" / "chat.json").read_text(encoding="utf-8") == "keep"
    assert not (tmp_path / "ecosystem" / "defaultspack").exists()
    current = json.loads((managed / "defaultspack" / "current.json").read_text(encoding="utf-8"))
    assert current["version"] == "2.5.0"
    assert old.is_dir()


def test_rollback_restores_previous_active_version(tmp_path):
    managed = tmp_path / "user_data" / "packs"
    _write_pack_dir(managed / "defaultspack" / "versions" / "2.4.1", version="2.4.1")
    _write_pack_dir(managed / "defaultspack" / "versions" / "2.5.0", version="2.5.0")
    from core_runtime.pack_seed import write_current_pointer_atomic

    write_current_pointer_atomic("defaultspack", "2.5.0", Path("versions") / "2.5.0", managed)
    manager = PackUpdateManager(managed_dir=managed, pack_state_dir=tmp_path / "pack_state")

    result = manager.rollback_pack("defaultspack")

    assert result.rolled_back is True
    assert result.active_version == "2.4.1"
    current = json.loads((managed / "defaultspack" / "current.json").read_text(encoding="utf-8"))
    assert current["version"] == "2.4.1"


def test_force_reinstall_replaces_existing_version_with_backup(tmp_path):
    managed = tmp_path / "user_data" / "packs"
    existing = _write_pack_dir(managed / "defaultspack" / "versions" / "2.5.0", version="2.5.0")
    (existing / "module.py").write_text("VALUE = 'old'\n", encoding="utf-8")
    from core_runtime.pack_seed import write_current_pointer_atomic

    write_current_pointer_atomic("defaultspack", "2.5.0", Path("versions") / "2.5.0", managed)
    source = _write_pack_dir(tmp_path / "src", version="2.5.0")
    (source / "module.py").write_text("VALUE = 'new'\n", encoding="utf-8")
    bundle = _bundle_from_dir(source, tmp_path / "defaultspack-2.5.0.rumi-pack")
    manager = PackUpdateManager(
        managed_dir=managed,
        pack_state_dir=tmp_path / "pack_state",
        index_url=f"file://{_index(tmp_path, bundle)}",
        trust_roots_path=_trust(tmp_path),
    )

    result = manager.apply_pack("defaultspack", force=True)

    assert result.applied is True
    assert result.backup_dir is not None
    assert Path(result.backup_dir).is_dir()
    assert (managed / "defaultspack" / "versions" / "2.5.0" / "module.py").read_text(encoding="utf-8") == "VALUE = 'new'\n"
    current = json.loads((managed / "defaultspack" / "current.json").read_text(encoding="utf-8"))
    assert current["version"] == "2.5.0"


def test_rollback_uses_semver_order_for_previous_version(tmp_path):
    managed = tmp_path / "user_data" / "packs"
    _write_pack_dir(managed / "defaultspack" / "versions" / "2.9.0", version="2.9.0")
    _write_pack_dir(managed / "defaultspack" / "versions" / "2.10.0", version="2.10.0")
    from core_runtime.pack_seed import write_current_pointer_atomic

    write_current_pointer_atomic("defaultspack", "2.10.0", Path("versions") / "2.10.0", managed)
    manager = PackUpdateManager(managed_dir=managed, pack_state_dir=tmp_path / "pack_state")

    result = manager.rollback_pack("defaultspack")

    assert result.active_version == "2.9.0"


def test_pack_auto_update_applies_only_official_packs(tmp_path):
    class FakePackUpdateManager(PackUpdateManager):
        def __init__(self, *, third_party_enabled: bool):
            super().__init__(managed_dir=tmp_path / "packs", pack_state_dir=tmp_path / "pack_state")
            self.third_party_enabled = third_party_enabled
            self.applied: list[str] = []
            self.written = None

        def read_update_preferences(self):
            return {
                "auto_update": {
                    "viewer": False,
                    "core": False,
                    "official_packs": True,
                    "third_party_packs": self.third_party_enabled,
                },
                "channels": {"viewer": "stable", "core": "stable", "packs": "stable"},
                "check_interval_hours": 24,
                "last_checked_at": None,
                "last_results": [],
                "updated_at": None,
            }

        def write_update_preferences(self, settings):
            self.written = settings
            return settings

        def _auto_update_due(self, settings):
            return True

        def check_all(self, channel="stable"):
            return [
                PackUpdateCheck(
                    target="pack:defaultspack",
                    pack_id="defaultspack",
                    current_version="2.4.1",
                    latest_version="2.5.0",
                    update_available=True,
                ),
                PackUpdateCheck(
                    target="pack:custompack",
                    pack_id="custompack",
                    current_version="0.1.0",
                    latest_version="0.2.0",
                    update_available=True,
                ),
            ]

        def apply_pack(self, pack_id, version=None, channel="stable", force=False):
            self.applied.append(pack_id)
            return PackUpdateResult(
                target=f"pack:{pack_id}",
                pack_id=pack_id,
                current_version="old",
                latest_version="new",
                applied=True,
                staged=True,
            )

    for third_party_enabled in (False, True):
        manager = FakePackUpdateManager(third_party_enabled=third_party_enabled)
        result = manager.run_auto_updates_once(force=True)
        statuses = {item["target"]: item["status"] for item in result.results}

        assert manager.applied == ["defaultspack"]
        assert statuses["pack:defaultspack"] == "applied"
        assert statuses["pack:custompack"] == "manual_required"
