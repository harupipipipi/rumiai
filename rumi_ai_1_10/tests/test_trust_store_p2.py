"""
test_trust_store_p2.py – Wave 6-D: add_trust validation & hot-reload tests.
"""
from __future__ import annotations

import json
import os
import time

import pytest

from core_runtime.unit_trust_store import UnitTrustStore

# A well-formed sha256 hex string for test use
VALID_SHA = "a" * 64


# =====================================================================
# Helpers
# =====================================================================

def _make_store(tmp_path, entries=None, auto_reload=False):
    """Create a UnitTrustStore pointed at *tmp_path* with optional seed data."""
    trust_dir = str(tmp_path)
    store = UnitTrustStore(trust_dir=trust_dir, auto_reload=auto_reload)
    if entries:
        trust_file = tmp_path / "trusted_units.json"
        trust_file.write_text(
            json.dumps({"version": "1.0", "trusted": entries}, ensure_ascii=False),
            encoding="utf-8",
        )
    return store


def _write_trust_file(tmp_path, entries):
    """Write (or overwrite) trusted_units.json with the given entries."""
    trust_file = tmp_path / "trusted_units.json"
    trust_file.write_text(
        json.dumps({"version": "1.0", "trusted": entries}, ensure_ascii=False),
        encoding="utf-8",
    )


# =====================================================================
# A-20: add_trust input validation
# =====================================================================

class TestAddTrustValidation:
    """add_trust() must reject invalid inputs with ValueError."""

    def test_add_trust_empty_unit_id(self, tmp_path):
        store = _make_store(tmp_path)
        store.load()
        with pytest.raises(ValueError, match="unit_id"):
            store.add_trust(unit_id="", version="1.0", sha256=VALID_SHA)

    def test_add_trust_empty_version(self, tmp_path):
        store = _make_store(tmp_path)
        store.load()
        with pytest.raises(ValueError, match="version"):
            store.add_trust(unit_id="u1", version="", sha256=VALID_SHA)

    def test_add_trust_invalid_sha256_short(self, tmp_path):
        store = _make_store(tmp_path)
        store.load()
        with pytest.raises(ValueError, match="sha256"):
            store.add_trust(unit_id="u1", version="1.0", sha256="abcd")

    def test_add_trust_invalid_sha256_nonhex(self, tmp_path):
        store = _make_store(tmp_path)
        store.load()
        bad_sha = "g" * 64  # 'g' is not hex
        with pytest.raises(ValueError, match="sha256"):
            store.add_trust(unit_id="u1", version="1.0", sha256=bad_sha)

    def test_add_trust_valid(self, tmp_path):
        store = _make_store(tmp_path)
        store.load()
        result = store.add_trust(unit_id="u1", version="1.0", sha256=VALID_SHA)
        assert result is True
        check = store.is_trusted("u1", "1.0", VALID_SHA)
        assert check.trusted is True

    def test_add_trust_none_note(self, tmp_path):
        store = _make_store(tmp_path)
        store.load()
        result = store.add_trust(
            unit_id="u1", version="1.0", sha256=VALID_SHA, note=None,
        )
        assert result is True
        entries = store.list_trusted()
        assert len(entries) == 1
        assert entries[0].note == ""


# =====================================================================
# A-15: Hot-reload
# =====================================================================

class TestHotReload:
    """reload_if_modified / auto_reload / cache_version tests."""

    def test_reload_if_modified_no_change(self, tmp_path):
        store = _make_store(tmp_path, entries=[])
        store.load()
        assert store.reload_if_modified() is False

    def test_reload_if_modified_after_external_change(self, tmp_path):
        store = _make_store(tmp_path, entries=[])
        store.load()

        # Externally add an entry and bump mtime
        new_sha = "b" * 64
        _write_trust_file(tmp_path, [
            {"unit_id": "ext", "version": "2.0", "sha256": new_sha},
        ])
        # Ensure mtime differs (some FS have 1-second resolution)
        trust_file = tmp_path / "trusted_units.json"
        new_mtime = trust_file.stat().st_mtime + 2
        os.utime(str(trust_file), (new_mtime, new_mtime))

        assert store.reload_if_modified() is True
        check = store.is_trusted("ext", "2.0", new_sha)
        assert check.trusted is True

    def test_auto_reload_flag(self, tmp_path):
        store = _make_store(tmp_path, entries=[], auto_reload=True)
        store.load()

        # Not trusted yet
        new_sha = "c" * 64
        check = store.is_trusted("auto", "3.0", new_sha)
        assert check.trusted is False

        # Externally add entry
        _write_trust_file(tmp_path, [
            {"unit_id": "auto", "version": "3.0", "sha256": new_sha},
        ])
        trust_file = tmp_path / "trusted_units.json"
        new_mtime = trust_file.stat().st_mtime + 2
        os.utime(str(trust_file), (new_mtime, new_mtime))

        # is_trusted with auto_reload should pick it up
        check = store.is_trusted("auto", "3.0", new_sha)
        assert check.trusted is True

    def test_cache_version_increment_on_reload(self, tmp_path):
        store = _make_store(tmp_path, entries=[])
        store.load()
        v_before = store.cache_version

        _write_trust_file(tmp_path, [
            {"unit_id": "cv", "version": "1.0", "sha256": "d" * 64},
        ])
        trust_file = tmp_path / "trusted_units.json"
        new_mtime = trust_file.stat().st_mtime + 2
        os.utime(str(trust_file), (new_mtime, new_mtime))

        store.reload_if_modified()
        assert store.cache_version > v_before


# =====================================================================
# Bugfix: load() failure must NOT increment _cache_version
# =====================================================================

class TestLoadCacheVersionBugfix:
    """load() failure should leave _cache_version unchanged."""

    def test_load_failure_no_cache_version_increment(self, tmp_path):
        trust_file = tmp_path / "trusted_units.json"
        trust_file.write_text("NOT VALID JSON", encoding="utf-8")

        store = UnitTrustStore(trust_dir=str(tmp_path))
        v_before = store.cache_version
        result = store.load()
        assert result is False
        assert store.cache_version == v_before
