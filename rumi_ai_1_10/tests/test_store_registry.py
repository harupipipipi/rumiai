"""
test_store_registry.py — store_registry.py のユニットテスト

テスト対象:
- ユーティリティ関数: _validate_store_path, _validate_key, _normalize_value_hash
- データクラス: StoreDefinition, StoreResult
- StoreRegistry: CRUD, CAS, list_keys, batch_get, audit_store_usage,
                 create_store_for_pack
"""
from __future__ import annotations

import json
import hashlib
import sqlite3
from pathlib import Path
from typing import Any
from unittest.mock import patch, MagicMock

import pytest

from core_runtime.store_registry import (
    _validate_store_path,
    _validate_key,
    _normalize_value_hash,
    _KEY_PATTERN,
    StoreDefinition,
    StoreResult,
    StoreRegistry,
    STORES_BASE_DIR,
    MAX_STORES_PER_PACK,
    MAX_VALUE_BYTES_CAS,
    _EXPECT_MISSING,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def store_dir(tmp_path: Path) -> Path:
    """テスト用のストアベースディレクトリを作成する。"""
    d = tmp_path / "user_data" / "stores"
    d.mkdir(parents=True)
    return d


@pytest.fixture()
def registry(tmp_path: Path, store_dir: Path, monkeypatch) -> StoreRegistry:
    """テスト用 StoreRegistry を返す。

    - DB を tmp_path に作成
    - STORES_BASE_DIR を tmp_path 配下に差し替え
    - store_migration の関数をモック
    """
    db_path = store_dir / "stores.db"

    # STORES_BASE_DIR を差し替え（_validate_store_path で使用）
    monkeypatch.setattr(
        "core_runtime.store_registry.STORES_BASE_DIR", store_dir
    )

    # store_migration のモック（相対インポートを迂回）
    with patch(
        "core_runtime.store_migration.cleanup_stale_tmp",
        return_value=None,
    ), patch(
        "core_runtime.store_migration.migrate_json_to_sqlite",
        return_value=False,
    ):
        reg = StoreRegistry(db_path=str(db_path))

    yield reg
    reg.close()


def _root(store_dir: Path, name: str) -> str:
    """store_dir 配下の root_path を返す。"""
    return str(store_dir / name)


# ---------------------------------------------------------------------------
# 1-2. _validate_store_path
# ---------------------------------------------------------------------------

class TestValidateStorePath:
    def test_valid_path(self, store_dir: Path, monkeypatch) -> None:
        monkeypatch.setattr(
            "core_runtime.store_registry.STORES_BASE_DIR", store_dir
        )
        p = store_dir / "my_store"
        p.mkdir()
        assert _validate_store_path(str(p)) is None

    def test_traversal_double_dot(self, store_dir: Path, monkeypatch) -> None:
        monkeypatch.setattr(
            "core_runtime.store_registry.STORES_BASE_DIR", store_dir
        )
        assert _validate_store_path(str(store_dir / "..")) is not None

    def test_outside_base_dir(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(
            "core_runtime.store_registry.STORES_BASE_DIR",
            tmp_path / "user_data" / "stores",
        )
        assert _validate_store_path("/tmp/evil") is not None


# ---------------------------------------------------------------------------
# 3-4. _validate_key
# ---------------------------------------------------------------------------

class TestValidateKey:
    @pytest.mark.parametrize("key", [
        "simple",
        "with/slash",
        "with.dot",
        "with:colon",
        "with-dash",
        "with_under",
        "a" * 512,
    ])
    def test_valid_keys(self, key: str) -> None:
        assert _validate_key(key) is None

    @pytest.mark.parametrize("key", [
        "",
        "a" * 513,
        "with space",
        "with@at",
        123,
        None,
    ])
    def test_invalid_keys(self, key) -> None:
        assert _validate_key(key) is not None


# ---------------------------------------------------------------------------
# 5. _normalize_value_hash
# ---------------------------------------------------------------------------

class TestNormalizeValueHash:
    def test_deterministic(self) -> None:
        """同じ値 → 同じハッシュ"""
        v = {"b": 2, "a": 1}
        h1 = _normalize_value_hash(v)
        h2 = _normalize_value_hash(v)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_key_order_independent(self) -> None:
        """キー順序が異なっても同じハッシュ（sort_keys=True）"""
        assert _normalize_value_hash({"a": 1, "b": 2}) == _normalize_value_hash({"b": 2, "a": 1})

    def test_different_values_different_hash(self) -> None:
        assert _normalize_value_hash({"a": 1}) != _normalize_value_hash({"a": 2})

    def test_matches_manual_computation(self) -> None:
        value = {"key": "val"}
        canonical = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        assert _normalize_value_hash(value) == expected


# ---------------------------------------------------------------------------
# 6. StoreDefinition
# ---------------------------------------------------------------------------

class TestStoreDefinition:
    def test_to_dict_from_dict_roundtrip(self) -> None:
        sd = StoreDefinition(
            store_id="test_store",
            root_path="/tmp/stores/test_store",
            created_at="2025-01-01T00:00:00Z",
            created_by="unit_test",
        )
        d = sd.to_dict()
        restored = StoreDefinition.from_dict(d)
        assert restored.store_id == sd.store_id
        assert restored.root_path == sd.root_path
        assert restored.created_at == sd.created_at
        assert restored.created_by == sd.created_by


# ---------------------------------------------------------------------------
# 7. StoreResult
# ---------------------------------------------------------------------------

class TestStoreResult:
    def test_success_to_dict(self) -> None:
        sr = StoreResult(success=True, store_id="s1")
        d = sr.to_dict()
        assert d["success"] is True
        assert d["store_id"] == "s1"
        assert d["error"] is None

    def test_error_to_dict(self) -> None:
        sr = StoreResult(success=False, store_id="s1", error="bad")
        d = sr.to_dict()
        assert d["success"] is False
        assert d["error"] == "bad"


# ---------------------------------------------------------------------------
# 8-10. StoreRegistry.create_store
# ---------------------------------------------------------------------------

class TestCreateStore:
    def test_create_success(self, registry: StoreRegistry, store_dir: Path) -> None:
        rp = _root(store_dir, "mystore")
        result = registry.create_store("mystore", rp, created_by="test")
        assert result.success is True
        assert result.store_id == "mystore"

    def test_create_invalid_store_id(self, registry: StoreRegistry, store_dir: Path) -> None:
        rp = _root(store_dir, "bad")
        result = registry.create_store("bad store id!", rp)
        assert result.success is False
        assert "must match" in result.error

    def test_create_empty_store_id(self, registry: StoreRegistry, store_dir: Path) -> None:
        rp = _root(store_dir, "x")
        result = registry.create_store("", rp)
        assert result.success is False

    def test_create_empty_root_path(self, registry: StoreRegistry) -> None:
        result = registry.create_store("valid_id", "")
        assert result.success is False
        assert "root_path is required" in result.error

    def test_create_duplicate(self, registry: StoreRegistry, store_dir: Path) -> None:
        rp = _root(store_dir, "dup")
        r1 = registry.create_store("dup", rp)
        assert r1.success is True
        r2 = registry.create_store("dup", rp)
        assert r2.success is False
        assert "already exists" in r2.error


# ---------------------------------------------------------------------------
# 11-12. StoreRegistry.get_store
# ---------------------------------------------------------------------------

class TestGetStore:
    def test_get_existing(self, registry: StoreRegistry, store_dir: Path) -> None:
        rp = _root(store_dir, "found")
        registry.create_store("found", rp, created_by="tester")
        sd = registry.get_store("found")
        assert sd is not None
        assert sd.store_id == "found"
        assert sd.created_by == "tester"

    def test_get_nonexistent(self, registry: StoreRegistry) -> None:
        assert registry.get_store("does_not_exist") is None


# ---------------------------------------------------------------------------
# 13. StoreRegistry.list_stores
# ---------------------------------------------------------------------------

class TestListStores:
    def test_list_multiple(self, registry: StoreRegistry, store_dir: Path) -> None:
        for name in ["alpha", "beta", "gamma"]:
            registry.create_store(name, _root(store_dir, name))
        stores = registry.list_stores()
        ids = {s["store_id"] for s in stores}
        assert ids == {"alpha", "beta", "gamma"}

    def test_list_empty(self, registry: StoreRegistry) -> None:
        assert registry.list_stores() == []


# ---------------------------------------------------------------------------
# 14-15. StoreRegistry.delete_store
# ---------------------------------------------------------------------------

class TestDeleteStore:
    def test_delete_success(self, registry: StoreRegistry, store_dir: Path) -> None:
        rp = _root(store_dir, "todel")
        registry.create_store("todel", rp)
        result = registry.delete_store("todel")
        assert result.success is True
        assert registry.get_store("todel") is None

    def test_delete_nonexistent(self, registry: StoreRegistry) -> None:
        result = registry.delete_store("ghost")
        assert result.success is False
        assert "not found" in result.error.lower()

    def test_delete_with_files(self, registry: StoreRegistry, store_dir: Path) -> None:
        rp = _root(store_dir, "withfiles")
        registry.create_store("withfiles", rp)
        (Path(rp) / "data.txt").write_text("hello")
        result = registry.delete_store("withfiles", delete_files=True)
        assert result.success is True
        assert not Path(rp).exists()


# ---------------------------------------------------------------------------
# 16-19. StoreRegistry.cas (Compare-And-Swap)
# ---------------------------------------------------------------------------

class TestCAS:
    def _setup_store(self, registry: StoreRegistry, store_dir: Path, sid: str = "cas_store") -> str:
        rp = _root(store_dir, sid)
        registry.create_store(sid, rp)
        return sid

    def test_cas_create_new_key(self, registry: StoreRegistry, store_dir: Path) -> None:
        """expected_value 省略 + キー不存在 → 新規作成成功"""
        sid = self._setup_store(registry, store_dir)
        result = registry.cas(sid, "mykey", new_value={"hello": "world"})
        assert result["success"] is True

    def test_cas_update_existing(self, registry: StoreRegistry, store_dir: Path) -> None:
        """既存キーの値一致 → 更新成功"""
        sid = self._setup_store(registry, store_dir)
        registry.cas(sid, "k1", new_value="v1")
        result = registry.cas(sid, "k1", expected_value="v1", new_value="v2")
        assert result["success"] is True

    def test_cas_conflict_value_mismatch(self, registry: StoreRegistry, store_dir: Path) -> None:
        """既存キーの値不一致 → conflict"""
        sid = self._setup_store(registry, store_dir)
        registry.cas(sid, "k1", new_value="v1")
        result = registry.cas(sid, "k1", expected_value="wrong", new_value="v2")
        assert result["success"] is False
        assert result["error_type"] == "conflict"

    def test_cas_conflict_key_exists_but_expected_missing(self, registry: StoreRegistry, store_dir: Path) -> None:
        """expected_value 省略 + キーが既に存在 → conflict"""
        sid = self._setup_store(registry, store_dir)
        registry.cas(sid, "k1", new_value="v1")
        result = registry.cas(sid, "k1", new_value="v2")
        assert result["success"] is False
        assert result["error_type"] == "conflict"

    def test_cas_no_new_value(self, registry: StoreRegistry, store_dir: Path) -> None:
        """new_value 未指定 → validation_error"""
        sid = self._setup_store(registry, store_dir)
        result = registry.cas(sid, "mykey")
        assert result["success"] is False
        assert result["error_type"] == "validation_error"

    def test_cas_store_not_found(self, registry: StoreRegistry) -> None:
        result = registry.cas("nonexistent", "key", new_value="val")
        assert result["success"] is False
        assert result["error_type"] == "store_not_found"

    def test_cas_invalid_key(self, registry: StoreRegistry, store_dir: Path) -> None:
        sid = self._setup_store(registry, store_dir)
        result = registry.cas(sid, "invalid key with spaces", new_value="x")
        assert result["success"] is False
        assert result["error_type"] == "validation_error"

    def test_cas_value_too_large(self, registry: StoreRegistry, store_dir: Path) -> None:
        sid = self._setup_store(registry, store_dir)
        huge = "x" * (MAX_VALUE_BYTES_CAS + 1)
        result = registry.cas(sid, "bigkey", new_value=huge)
        assert result["success"] is False
        assert result["error_type"] == "payload_too_large"

    def test_cas_expected_none_means_json_null(self, registry: StoreRegistry, store_dir: Path) -> None:
        """expected_value=None は JSON null を期待する意味"""
        sid = self._setup_store(registry, store_dir)
        registry.cas(sid, "nullkey", new_value=None)
        result = registry.cas(sid, "nullkey", expected_value=None, new_value="updated")
        assert result["success"] is True


# ---------------------------------------------------------------------------
# 20. list_keys
# ---------------------------------------------------------------------------

class TestListKeys:
    def test_list_all_keys(self, registry: StoreRegistry, store_dir: Path) -> None:
        sid = "liststore"
        registry.create_store(sid, _root(store_dir, sid))
        for i in range(5):
            registry.cas(sid, f"key{i}", new_value=f"val{i}")
        result = registry.list_keys(sid)
        assert result["success"] is True
        assert len(result["keys"]) == 5
        assert result["has_more"] is False

    def test_list_keys_with_pagination(self, registry: StoreRegistry, store_dir: Path) -> None:
        sid = "pagstore"
        registry.create_store(sid, _root(store_dir, sid))
        for i in range(10):
            registry.cas(sid, f"k{i:02d}", new_value=i)
        result = registry.list_keys(sid, limit=3)
        assert result["success"] is True
        assert len(result["keys"]) == 3
        assert result["has_more"] is True
        assert result["next_cursor"] is not None

        result2 = registry.list_keys(sid, limit=3, cursor=result["next_cursor"])
        assert result2["success"] is True
        assert len(result2["keys"]) == 3
        assert set(result["keys"]).isdisjoint(set(result2["keys"]))

    def test_list_keys_with_prefix(self, registry: StoreRegistry, store_dir: Path) -> None:
        sid = "prefixstore"
        registry.create_store(sid, _root(store_dir, sid))
        registry.cas(sid, "data/a", new_value=1)
        registry.cas(sid, "data/b", new_value=2)
        registry.cas(sid, "meta/x", new_value=3)
        result = registry.list_keys(sid, prefix="data/")
        assert result["success"] is True
        assert set(result["keys"]) == {"data/a", "data/b"}

    def test_list_keys_store_not_found(self, registry: StoreRegistry) -> None:
        result = registry.list_keys("nope")
        assert result["success"] is False
        assert result["error_type"] == "store_not_found"


# ---------------------------------------------------------------------------
# 21. batch_get
# ---------------------------------------------------------------------------

class TestBatchGet:
    def test_batch_get_success(self, registry: StoreRegistry, store_dir: Path) -> None:
        sid = "batchstore"
        registry.create_store(sid, _root(store_dir, sid))
        registry.cas(sid, "a", new_value="alpha")
        registry.cas(sid, "b", new_value="beta")
        result = registry.batch_get(sid, ["a", "b", "c"])
        assert result["success"] is True
        assert result["results"]["a"] == "alpha"
        assert result["results"]["b"] == "beta"
        assert result["results"]["c"] is None
        assert result["found"] == 2
        assert result["not_found"] == 1

    def test_batch_get_empty_keys(self, registry: StoreRegistry, store_dir: Path) -> None:
        sid = "batchstore2"
        registry.create_store(sid, _root(store_dir, sid))
        result = registry.batch_get(sid, [])
        assert result["success"] is False
        assert result["error_type"] == "validation_error"

    def test_batch_get_too_many_keys(self, registry: StoreRegistry, store_dir: Path) -> None:
        sid = "batchstore3"
        registry.create_store(sid, _root(store_dir, sid))
        keys = [f"k{i}" for i in range(StoreRegistry.MAX_BATCH_KEYS + 1)]
        result = registry.batch_get(sid, keys)
        assert result["success"] is False
        assert "Too many keys" in result["error"]

    def test_batch_get_store_not_found(self, registry: StoreRegistry) -> None:
        result = registry.batch_get("nope", ["a"])
        assert result["success"] is False
        assert result["error_type"] == "store_not_found"


# ---------------------------------------------------------------------------
# audit_store_usage
# ---------------------------------------------------------------------------

class TestAuditStoreUsage:
    def test_audit_usage(self, registry: StoreRegistry, store_dir: Path) -> None:
        sid = "auditstore"
        registry.create_store(sid, _root(store_dir, sid))
        registry.cas(sid, "k1", new_value="small")
        registry.cas(sid, "k2", new_value="x" * 1000)
        result = registry.audit_store_usage(sid)
        assert result["store_id"] == sid
        assert result["key_count"] == 2
        assert result["total_size_bytes"] > 0
        assert result["largest_key"] == "k2"

    def test_audit_usage_not_found(self, registry: StoreRegistry) -> None:
        result = registry.audit_store_usage("nope")
        assert result["success"] is False


# ---------------------------------------------------------------------------
# create_store_for_pack
# ---------------------------------------------------------------------------

class TestCreateStoreForPack:
    def test_create_for_pack(self, registry: StoreRegistry, store_dir: Path) -> None:
        decl = [
            {"store_id": "chat"},
            {"store_id": "data"},
        ]
        results = registry.create_store_for_pack("mypack", decl)
        assert len(results) == 2
        assert all(r.success for r in results)
        assert results[0].store_id == "mypack__chat"
        assert results[1].store_id == "mypack__data"

    def test_create_for_pack_prefix_already_present(self, registry: StoreRegistry, store_dir: Path) -> None:
        decl = [{"store_id": "mypack__explicit"}]
        results = registry.create_store_for_pack("mypack", decl)
        assert len(results) == 1
        assert results[0].store_id == "mypack__explicit"

    def test_create_for_pack_too_many(self, registry: StoreRegistry, store_dir: Path) -> None:
        decl = [{"store_id": f"s{i}"} for i in range(MAX_STORES_PER_PACK + 1)]
        results = registry.create_store_for_pack("pack", decl)
        assert len(results) == 1
        assert results[0].success is False
        assert "Too many" in results[0].error

    def test_create_for_pack_empty(self, registry: StoreRegistry) -> None:
        results = registry.create_store_for_pack("pack", [])
        assert results == []

    def test_create_for_pack_idempotent(self, registry: StoreRegistry, store_dir: Path) -> None:
        """既にストアが存在する場合は成功扱い"""
        decl = [{"store_id": "chat"}]
        r1 = registry.create_store_for_pack("pk", decl)
        assert r1[0].success is True
        r2 = registry.create_store_for_pack("pk", decl)
        assert r2[0].success is True


# ---------------------------------------------------------------------------
# close / connection management
# ---------------------------------------------------------------------------

class TestConnection:
    def test_close_and_reopen(self, registry: StoreRegistry, store_dir: Path) -> None:
        """close() 後も再接続できる"""
        registry.create_store("ctest", _root(store_dir, "ctest"))
        registry.close()
        sd = registry.get_store("ctest")
        assert sd is not None
        assert sd.store_id == "ctest"
