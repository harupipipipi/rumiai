"""
test_capability_trust_store.py - P0: CapabilityTrustStore のテスト

対象: core_runtime/capability_trust_store.py
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core_runtime.capability_trust_store import (
    CapabilityTrustStore,
    TrustCheckResult,
    TrustedHandler,
)

VALID_SHA = "a" * 64
OTHER_SHA = "b" * 64


# ===================================================================
# add_trust
# ===================================================================

class TestAddTrust:

    def test_add_valid_handler(self, tmp_path):
        store = CapabilityTrustStore(trust_dir=str(tmp_path / "trust"))
        store.load()
        assert store.add_trust("handler_a", VALID_SHA, "test note") is True
        result = store.is_trusted("handler_a", VALID_SHA)
        assert result.trusted is True

    def test_add_trust_persists_to_file(self, tmp_path):
        trust_dir = str(tmp_path / "trust")
        store = CapabilityTrustStore(trust_dir=trust_dir)
        store.load()
        store.add_trust("handler_a", VALID_SHA)

        trust_file = Path(trust_dir) / "trusted_handlers.json"
        assert trust_file.exists()
        data = json.loads(trust_file.read_text(encoding="utf-8"))
        assert len(data["trusted"]) == 1
        assert data["trusted"][0]["handler_id"] == "handler_a"

    def test_add_trust_normalizes_sha_to_lowercase(self, tmp_path):
        store = CapabilityTrustStore(trust_dir=str(tmp_path / "trust"))
        store.load()
        upper_sha = "A" * 64
        store.add_trust("handler_a", upper_sha)
        result = store.is_trusted("handler_a", upper_sha)
        assert result.trusted is True
        assert result.expected_sha256 == VALID_SHA

    def test_reject_invalid_sha_length(self, tmp_path):
        store = CapabilityTrustStore(trust_dir=str(tmp_path / "trust"))
        store.load()
        assert store.add_trust("handler_a", "abc123") is False

    def test_reject_non_hex_sha(self, tmp_path):
        store = CapabilityTrustStore(trust_dir=str(tmp_path / "trust"))
        store.load()
        assert store.add_trust("handler_a", "g" * 64) is False

    def test_reject_empty_handler_id(self, tmp_path):
        store = CapabilityTrustStore(trust_dir=str(tmp_path / "trust"))
        store.load()
        assert store.add_trust("", VALID_SHA) is False

    def test_overwrite_existing_handler(self, tmp_path):
        store = CapabilityTrustStore(trust_dir=str(tmp_path / "trust"))
        store.load()
        store.add_trust("handler_a", VALID_SHA)
        store.add_trust("handler_a", OTHER_SHA)
        result = store.is_trusted("handler_a", VALID_SHA)
        assert result.trusted is False
        result2 = store.is_trusted("handler_a", OTHER_SHA)
        assert result2.trusted is True


# ===================================================================
# is_trusted
# ===================================================================

class TestIsTrusted:

    def test_trusted_match(self, tmp_path):
        store = CapabilityTrustStore(trust_dir=str(tmp_path / "trust"))
        store.load()
        store.add_trust("handler_a", VALID_SHA)
        result = store.is_trusted("handler_a", VALID_SHA)
        assert result.trusted is True
        assert result.reason == "Trusted"

    def test_sha_mismatch(self, tmp_path):
        store = CapabilityTrustStore(trust_dir=str(tmp_path / "trust"))
        store.load()
        store.add_trust("handler_a", VALID_SHA)
        result = store.is_trusted("handler_a", OTHER_SHA)
        assert result.trusted is False
        assert "mismatch" in result.reason.lower()

    def test_unknown_handler(self, tmp_path):
        store = CapabilityTrustStore(trust_dir=str(tmp_path / "trust"))
        store.load()
        result = store.is_trusted("nonexistent", VALID_SHA)
        assert result.trusted is False
        assert "not in trust list" in result.reason

    def test_store_not_loaded(self, tmp_path):
        store = CapabilityTrustStore(trust_dir=str(tmp_path / "trust"))
        # Intentionally not calling load()
        result = store.is_trusted("handler_a", VALID_SHA)
        assert result.trusted is False
        assert "not loaded" in result.reason.lower()

    def test_case_insensitive_sha(self, tmp_path):
        store = CapabilityTrustStore(trust_dir=str(tmp_path / "trust"))
        store.load()
        store.add_trust("handler_a", VALID_SHA)
        result = store.is_trusted("handler_a", "A" * 64)
        assert result.trusted is True


# ===================================================================
# load
# ===================================================================

class TestLoad:

    def test_load_empty_dir(self, tmp_path):
        store = CapabilityTrustStore(trust_dir=str(tmp_path / "trust"))
        assert store.load() is True
        assert store.is_loaded() is True
        assert store.list_trusted() == []

    def test_load_from_file(self, tmp_path):
        trust_dir = tmp_path / "trust"
        trust_dir.mkdir(parents=True)
        trust_file = trust_dir / "trusted_handlers.json"
        trust_file.write_text(json.dumps({
            "version": "1.0",
            "trusted": [
                {"handler_id": "h1", "sha256": VALID_SHA, "note": "test"},
                {"handler_id": "h2", "sha256": OTHER_SHA},
            ],
        }), encoding="utf-8")

        store = CapabilityTrustStore(trust_dir=str(trust_dir))
        assert store.load() is True
        assert len(store.list_trusted()) == 2

    def test_load_malformed_json(self, tmp_path):
        trust_dir = tmp_path / "trust"
        trust_dir.mkdir(parents=True)
        trust_file = trust_dir / "trusted_handlers.json"
        trust_file.write_text("NOT JSON", encoding="utf-8")

        store = CapabilityTrustStore(trust_dir=str(trust_dir))
        assert store.load() is False
        assert store.get_load_error() is not None

    def test_load_invalid_sha_in_file(self, tmp_path):
        trust_dir = tmp_path / "trust"
        trust_dir.mkdir(parents=True)
        trust_file = trust_dir / "trusted_handlers.json"
        trust_file.write_text(json.dumps({
            "trusted": [{"handler_id": "h1", "sha256": "short"}],
        }), encoding="utf-8")

        store = CapabilityTrustStore(trust_dir=str(trust_dir))
        assert store.load() is False

    def test_load_missing_handler_id(self, tmp_path):
        trust_dir = tmp_path / "trust"
        trust_dir.mkdir(parents=True)
        trust_file = trust_dir / "trusted_handlers.json"
        trust_file.write_text(json.dumps({
            "trusted": [{"sha256": VALID_SHA}],
        }), encoding="utf-8")

        store = CapabilityTrustStore(trust_dir=str(trust_dir))
        assert store.load() is False


# ===================================================================
# remove_trust
# ===================================================================

class TestRemoveTrust:

    def test_remove_existing(self, tmp_path):
        store = CapabilityTrustStore(trust_dir=str(tmp_path / "trust"))
        store.load()
        store.add_trust("handler_a", VALID_SHA)
        assert store.remove_trust("handler_a") is True
        result = store.is_trusted("handler_a", VALID_SHA)
        assert result.trusted is False

    def test_remove_nonexistent(self, tmp_path):
        store = CapabilityTrustStore(trust_dir=str(tmp_path / "trust"))
        store.load()
        assert store.remove_trust("nonexistent") is False


# ===================================================================
# Persistence round-trip
# ===================================================================

class TestPersistence:

    def test_add_reload_check(self, tmp_path):
        trust_dir = str(tmp_path / "trust")
        store1 = CapabilityTrustStore(trust_dir=trust_dir)
        store1.load()
        store1.add_trust("handler_a", VALID_SHA, "note A")
        store1.add_trust("handler_b", OTHER_SHA, "note B")

        store2 = CapabilityTrustStore(trust_dir=trust_dir)
        assert store2.load() is True
        assert store2.is_trusted("handler_a", VALID_SHA).trusted is True
        assert store2.is_trusted("handler_b", OTHER_SHA).trusted is True
        assert len(store2.list_trusted()) == 2
