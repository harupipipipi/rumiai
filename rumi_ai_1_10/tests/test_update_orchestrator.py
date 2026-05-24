from __future__ import annotations

import base64
import json
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core_runtime.update.download import sha256_file
from core_runtime.update.core_update_manager import CoreUpdateManager, CoreUpdateError
from core_runtime.update.models import CoreUpdateResult, PackUpdateCheck, PackUpdateResult
from core_runtime.update.pack_update_manager import PackUpdateManager
from core_runtime.update.trust import (
    core_bundle_signature_payload,
    index_signature_payload,
    public_key_to_b64,
    sign_ed25519,
    signature_entry,
)
from core_runtime.update.update_orchestrator import UpdateOrchestrator


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


def _trust(tmp_path: Path) -> Path:
    path = tmp_path / "trust_roots.json"
    path.write_text(
        json.dumps({"schema": "rumi.trust_roots.v1", "ed25519_public_keys": {_TEST_KEY_ID: _TEST_PUBLIC_KEY}}),
        encoding="utf-8",
    )
    return path


def _core_bundle(tmp_path: Path, version: str = "1.11.0", *, traversal: bool = False) -> Path:
    bundle = tmp_path / f"rumiai-core-{version}.zip"
    with zipfile.ZipFile(bundle, "w") as zf:
        zf.writestr("pyproject.toml", f'[project]\nversion = "{version}"\n')
        zf.writestr("app.py", "print('new')\n")
        if traversal:
            zf.writestr("../evil.py", "bad\n")
    return bundle


def _core_index(tmp_path: Path, bundle: Path, *, signature: str | None = None, sign_index: bool = True) -> Path:
    digest = sha256_file(bundle)
    version = "1.11.0"
    payload = {
        "schema": "rumi.core_index.v1",
        "generated_at": "2026-05-24T00:00:00Z",
        "latest": version,
        "versions": {
            version: {
                "url": f"file://{bundle}",
                "sha256": digest,
                "signature": signature if signature is not None else sign_ed25519(
                    core_bundle_signature_payload(version, digest),
                    _TEST_KEY_ID,
                    _TEST_PRIVATE_KEY,
                ),
                "signature_scheme": "ed25519",
                "key_id": _TEST_KEY_ID,
            }
        },
    }
    if sign_index:
        payload["signatures"] = [
            signature_entry(sign_ed25519(index_signature_payload(payload), _TEST_KEY_ID, _TEST_PRIVATE_KEY))
        ]
    index = tmp_path / "core-index.stable.json"
    index.write_text(json.dumps(payload), encoding="utf-8")
    return index


def test_core_update_rejects_pack_paths(tmp_path):
    base = tmp_path / "runtime"
    extracted = tmp_path / "bundle"
    extracted.mkdir()
    (extracted / "pyproject.toml").write_text('[project]\nversion = "1.11.0"\n', encoding="utf-8")
    (extracted / "packs").mkdir()
    (extracted / "packs" / "defaultspack.txt").write_text("bad", encoding="utf-8")
    manager = CoreUpdateManager(base_dir=base, user_data_dir=tmp_path / "user_data")

    try:
        manager._validate_extracted_core(extracted)
    except CoreUpdateError as exc:
        assert "protected path" in str(exc)
    else:
        raise AssertionError("core update accepted protected packs path")


def test_core_update_rejects_top_level_protected_file(tmp_path):
    base = tmp_path / "runtime"
    extracted = tmp_path / "bundle"
    extracted.mkdir()
    (extracted / "pyproject.toml").write_text('[project]\nversion = "1.11.0"\n', encoding="utf-8")
    (extracted / "pack_state").write_text("bad", encoding="utf-8")
    manager = CoreUpdateManager(base_dir=base, user_data_dir=tmp_path / "user_data")

    try:
        manager._validate_extracted_core(extracted)
    except CoreUpdateError as exc:
        assert "protected path" in str(exc)
    else:
        raise AssertionError("core update accepted protected root file")


def test_core_update_rejects_index_bundle_version_mismatch(tmp_path):
    base = tmp_path / "runtime"
    extracted = tmp_path / "bundle"
    extracted.mkdir()
    (extracted / "pyproject.toml").write_text('[project]\nversion = "1.10.0"\n', encoding="utf-8")
    manager = CoreUpdateManager(base_dir=base, user_data_dir=tmp_path / "user_data")

    try:
        manager._validate_extracted_core(extracted, expected_version="1.11.0")
    except CoreUpdateError as exc:
        assert "version mismatch" in str(exc)
    else:
        raise AssertionError("core update accepted mismatched bundle version")


def test_core_stage_rejects_unsigned_core_index(tmp_path):
    base = tmp_path / "runtime"
    base.mkdir()
    (base / "pyproject.toml").write_text('[project]\nversion = "1.10.0"\n', encoding="utf-8")
    bundle = _core_bundle(tmp_path)
    index = _core_index(tmp_path, bundle, sign_index=False)
    manager = CoreUpdateManager(
        base_dir=base,
        user_data_dir=tmp_path / "user_data",
        index_url=f"file://{index}",
        trust_roots_path=_trust(tmp_path),
    )

    with pytest.raises(CoreUpdateError, match="missing signature"):
        manager.stage_core()


def test_core_stage_ignores_user_added_pack_trust_roots(tmp_path, monkeypatch):
    official_roots = tmp_path / "empty_official_trust_roots.json"
    official_roots.write_text(
        json.dumps({"schema": "rumi.trust_roots.v1", "ed25519_public_keys": {}}),
        encoding="utf-8",
    )
    monkeypatch.setattr("core_runtime.update.trust.OFFICIAL_TRUST_ROOTS_PATH", official_roots)
    base = tmp_path / "runtime"
    base.mkdir()
    (base / "pyproject.toml").write_text('[project]\nversion = "1.10.0"\n', encoding="utf-8")
    bundle = _core_bundle(tmp_path)
    index = _core_index(tmp_path, bundle)
    manager = CoreUpdateManager(
        base_dir=base,
        user_data_dir=tmp_path / "user_data",
        index_url=f"file://{index}",
        trust_roots_path=_trust(tmp_path),
    )

    with pytest.raises(CoreUpdateError, match="unknown trust root"):
        manager.stage_core()


def test_core_stage_rejects_bad_bundle_signature_before_extract(tmp_path):
    base = tmp_path / "runtime"
    base.mkdir()
    (base / "pyproject.toml").write_text('[project]\nversion = "1.10.0"\n', encoding="utf-8")
    bundle = _core_bundle(tmp_path, traversal=True)
    index = _core_index(tmp_path, bundle, signature="ed25519:test:bad")
    manager = CoreUpdateManager(
        base_dir=base,
        user_data_dir=tmp_path / "user_data",
        index_url=f"file://{index}",
        trust_roots_path=_trust(tmp_path),
    )

    with pytest.raises(CoreUpdateError, match="signature"):
        manager.stage_core()


def test_core_apply_rejects_traversal_stage_id_from_body(tmp_path):
    base = tmp_path / "runtime"
    manager = CoreUpdateManager(base_dir=base, user_data_dir=tmp_path / "user_data")

    with pytest.raises(CoreUpdateError, match="invalid stage_id"):
        manager.apply_staged_core("../evil")

    assert not (tmp_path / "user_data" / "update_state" / "evil").exists()


def test_auto_update_due_uses_configured_check_interval(tmp_path):
    manager = PackUpdateManager(managed_dir=tmp_path / "packs", pack_state_dir=tmp_path / "pack_state")
    last_checked = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat().replace("+00:00", "Z")

    assert manager._auto_update_due({"last_checked_at": last_checked, "check_interval_hours": 1}) is True
    assert manager._auto_update_due({"last_checked_at": last_checked, "check_interval_hours": 24}) is False


def test_viewer_update_api_is_informational_and_does_not_touch_packs(tmp_path):
    packs = tmp_path / "user_data" / "packs"
    packs.mkdir(parents=True)
    before = sorted(packs.iterdir())

    result = UpdateOrchestrator().viewer_status()

    assert result["target"] == "viewer"
    assert result["rollback_available"] is False
    assert sorted(packs.iterdir()) == before


def test_layered_auto_update_runner_uses_pack_state_settings():
    class FakePackManager:
        def __init__(self):
            self.written = None

        def read_update_preferences(self):
            return {
                "auto_update": {
                    "viewer": True,
                    "core": True,
                    "official_packs": True,
                    "third_party_packs": True,
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
                )
            ]

        def apply_pack(self, pack_id, version=None, channel="stable", force=False):
            return PackUpdateResult(
                target=f"pack:{pack_id}",
                pack_id=pack_id,
                current_version="2.4.1",
                latest_version="2.5.0",
                applied=True,
                staged=True,
            )

    class FakeCoreManager:
        def check_core(self, channel="stable"):
            return CoreUpdateResult(
                target="core",
                current_version="1.10.0",
                latest_version="1.11.0",
                update_available=True,
            )

        def apply_core(self, version=None, channel="stable", force=False):
            return CoreUpdateResult(
                target="core",
                current_version="1.10.0",
                latest_version="1.11.0",
                applied=True,
                restart_required=True,
            )

    pack_manager = FakePackManager()
    result = UpdateOrchestrator(pack_manager=pack_manager, core_manager=FakeCoreManager()).run_auto_updates_once(
        force=True
    )

    statuses = {item["target"]: item["status"] for item in result.results}
    assert result.due is True
    assert result.enabled_targets == ["viewer", "core", "official_packs", "third_party_packs"]
    assert statuses["viewer"] == "handled_by_tauri"
    assert statuses["core"] == "applied"
    assert statuses["pack:defaultspack"] == "applied"
    assert statuses["third_party_packs"] == "manual_required"
    assert pack_manager.written["last_checked_at"] == result.checked_at
