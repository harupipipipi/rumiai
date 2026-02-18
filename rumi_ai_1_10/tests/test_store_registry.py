"""
test_store_registry.py - StoreRegistry のテスト (SQLite ベース)

対象: core_runtime/store_registry.py
"""
from __future__ import annotations

from pathlib import Path

import pytest

import core_runtime.store_registry as sr_module
from core_runtime.store_registry import StoreRegistry


# ===================================================================
# Fixture: STORES_BASE_DIR / STORES_INDEX_PATH を tmp_path にリダイレクト
# ===================================================================

@pytest.fixture(autouse=True)
def _patch_stores_paths(tmp_path, monkeypatch):
    """STORES_BASE_DIR / STORES_INDEX_PATH をテスト用 tmp_path にリダイレクト"""
    stores_base = tmp_path / "stores"
    stores_base.mkdir()
    monkeypatch.setattr(sr_module, "STORES_BASE_DIR", stores_base)
    # 存在しないパスにして JSON→SQLite migration を回避
    monkeypatch.setattr(
        sr_module, "STORES_INDEX_PATH", str(tmp_path / "nonexistent_index.json")
    )


def _make_registry(tmp_path: Path) -> StoreRegistry:
    """テスト用の StoreRegistry を作成する (SQLite ベース)"""
    db_path = str(tmp_path / "test_stores.db")
    return StoreRegistry(db_path=db_path)


# ===================================================================
# create_store
# ===================================================================

class TestCreateStore:

    def test_create_valid_store(self, tmp_path):
        reg = _make_registry(tmp_path)
        root = str(tmp_path / "stores" / "my-store")
        result = reg.create_store("my-store", root)
        assert result.success is True
        assert result.store_id == "my-store"
        assert Path(root).is_dir()

    def test_create_store_persists(self, tmp_path):
        db = str(tmp_path / "persist_test.db")
        root = str(tmp_path / "stores" / "my-store")
        reg1 = StoreRegistry(db_path=db)
        reg1.create_store("my-store", root)
        reg1.close()

        reg2 = StoreRegistry(db_path=db)
        assert reg2.get_store("my-store") is not None
        reg2.close()

    def test_reject_duplicate_store_id(self, tmp_path):
        reg = _make_registry(tmp_path)
        root = str(tmp_path / "stores" / "dup")
        reg.create_store("dup", root)
        result = reg.create_store("dup", root)
        assert result.success is False
        assert "already exists" in result.error

    def test_reject_empty_store_id(self, tmp_path):
        reg = _make_registry(tmp_path)
        result = reg.create_store("", str(tmp_path / "stores" / "x"))
        assert result.success is False

    def test_reject_invalid_store_id_chars(self, tmp_path):
        reg = _make_registry(tmp_path)
        result = reg.create_store("bad store!", str(tmp_path / "stores" / "x"))
        assert result.success is False

    def test_reject_store_id_too_long(self, tmp_path):
        reg = _make_registry(tmp_path)
        long_id = "a" * 129
        result = reg.create_store(long_id, str(tmp_path / "stores" / long_id))
        assert result.success is False

    def test_valid_store_id_chars(self, tmp_path):
        reg = _make_registry(tmp_path)
        sid = "My_Store-01"
        root = str(tmp_path / "stores" / sid)
        result = reg.create_store(sid, root)
        assert result.success is True


# ===================================================================
# Path traversal prevention
# ===================================================================

class TestPathTraversal:

    def test_reject_dotdot_in_root_path(self, tmp_path):
        reg = _make_registry(tmp_path)
        evil = str(tmp_path / "stores" / ".." / "escape")
        result = reg.create_store("evil", evil)
        assert result.success is False
        assert ".." in result.error

    def test_reject_root_outside_base_dir(self, tmp_path):
        reg = _make_registry(tmp_path)
        result = reg.create_store("evil", "/tmp/outside")
        assert result.success is False


# ===================================================================
# delete_store
# ===================================================================

class TestDeleteStore:

    def test_delete_existing_store(self, tmp_path):
        reg = _make_registry(tmp_path)
        root = str(tmp_path / "stores" / "del-me")
        reg.create_store("del-me", root)
        result = reg.delete_store("del-me")
        assert result.success is True
        assert reg.get_store("del-me") is None

    def test_delete_nonexistent_store(self, tmp_path):
        reg = _make_registry(tmp_path)
        result = reg.delete_store("nonexistent")
        assert result.success is False

    def test_delete_with_files(self, tmp_path):
        reg = _make_registry(tmp_path)
        root = tmp_path / "stores" / "del-files"
        root.mkdir(parents=True)
        (root / "data.json").write_text("{}", encoding="utf-8")
        reg.create_store("del-files", str(root))
        result = reg.delete_store("del-files", delete_files=True)
        assert result.success is True
        assert not root.exists()

    def test_delete_without_removing_files(self, tmp_path):
        reg = _make_registry(tmp_path)
        root = tmp_path / "stores" / "keep-files"
        root.mkdir(parents=True)
        (root / "data.json").write_text("{}", encoding="utf-8")
        reg.create_store("keep-files", str(root))
        reg.delete_store("keep-files", delete_files=False)
        assert root.exists()


# ===================================================================
# create_store_for_pack
# ===================================================================

class TestCreateStoreForPack:

    def test_prefix_enforcement(self, tmp_path):
        reg = _make_registry(tmp_path)
        results = reg.create_store_for_pack("mypack", [
            {"store_id": "data"},
        ])
        assert len(results) == 1
        assert results[0].success is True
        assert results[0].store_id == "mypack__data"
        assert reg.get_store("mypack__data") is not None

    def test_already_prefixed(self, tmp_path):
        reg = _make_registry(tmp_path)
        results = reg.create_store_for_pack("mypack", [
            {"store_id": "mypack__data"},
        ])
        assert len(results) == 1
        assert results[0].store_id == "mypack__data"

    def test_duplicate_store_is_success(self, tmp_path):
        reg = _make_registry(tmp_path)
        reg.create_store_for_pack("mypack", [{"store_id": "data"}])
        results = reg.create_store_for_pack("mypack", [{"store_id": "data"}])
        assert results[0].success is True

    def test_max_stores_per_pack(self, tmp_path):
        reg = _make_registry(tmp_path)
        stores = [{"store_id": f"s{i}"} for i in range(11)]
        results = reg.create_store_for_pack("mypack", stores)
        assert len(results) == 1
        assert results[0].success is False
        assert "Too many" in results[0].error

    def test_empty_declaration(self, tmp_path):
        reg = _make_registry(tmp_path)
        results = reg.create_store_for_pack("mypack", [])
        assert results == []


# ===================================================================
# list_stores / get_store
# ===================================================================

class TestListAndGet:

    def test_list_stores(self, tmp_path):
        reg = _make_registry(tmp_path)
        root1 = str(tmp_path / "stores" / "s1")
        root2 = str(tmp_path / "stores" / "s2")
        reg.create_store("s1", root1)
        reg.create_store("s2", root2)
        stores = reg.list_stores()
        ids = {s["store_id"] for s in stores}
        assert ids == {"s1", "s2"}

    def test_get_existing(self, tmp_path):
        reg = _make_registry(tmp_path)
        reg.create_store("s1", str(tmp_path / "stores" / "s1"))
        store = reg.get_store("s1")
        assert store is not None
        assert store.store_id == "s1"

    def test_get_nonexistent(self, tmp_path):
        reg = _make_registry(tmp_path)
        assert reg.get_store("nonexistent") is None


# ===================================================================
# CAS (Compare-And-Swap) — SQLite ベース (全プラットフォーム対応)
# ===================================================================

class TestCAS:

    def test_cas_create(self, tmp_path):
        reg = _make_registry(tmp_path)
        root = str(tmp_path / "stores" / "cas-store")
        reg.create_store("cas-store", root)
        result = reg.cas("cas-store", "mykey", new_value={"v": 1})
        assert result["success"] is True

    def test_cas_update(self, tmp_path):
        reg = _make_registry(tmp_path)
        root = str(tmp_path / "stores" / "cas-store")
        reg.create_store("cas-store", root)
        reg.cas("cas-store", "mykey", new_value={"v": 1})
        result = reg.cas("cas-store", "mykey", expected_value={"v": 1}, new_value={"v": 2})
        assert result["success"] is True

    def test_cas_conflict(self, tmp_path):
        reg = _make_registry(tmp_path)
        root = str(tmp_path / "stores" / "cas-store")
        reg.create_store("cas-store", root)
        reg.cas("cas-store", "mykey", new_value={"v": 1})
        result = reg.cas("cas-store", "mykey", expected_value={"v": 999}, new_value={"v": 2})
        assert result["success"] is False
        assert result["error_type"] == "conflict"

    def test_cas_key_not_exist_but_expected(self, tmp_path):
        reg = _make_registry(tmp_path)
        root = str(tmp_path / "stores" / "cas-store")
        reg.create_store("cas-store", root)
        result = reg.cas("cas-store", "nope", expected_value={"v": 1}, new_value={"v": 2})
        assert result["success"] is False
        assert result["error_type"] == "conflict"

    def test_cas_key_exists_but_expected_missing(self, tmp_path):
        """キーが既に存在するのに expected_value 省略 (= 不存在期待) で CAS → conflict"""
        reg = _make_registry(tmp_path)
        root = str(tmp_path / "stores" / "cas-store")
        reg.create_store("cas-store", root)
        reg.cas("cas-store", "mykey", new_value={"v": 1})
        # expected_value 省略 = _EXPECT_MISSING → キー存在で conflict
        result = reg.cas("cas-store", "mykey", new_value={"v": 2})
        assert result["success"] is False
        assert result["error_type"] == "conflict"

    def test_cas_store_not_found(self, tmp_path):
        reg = _make_registry(tmp_path)
        result = reg.cas("missing", "k", new_value=1)
        assert result["success"] is False

    def test_cas_invalid_key(self, tmp_path):
        """不正なキー (スペース含み) でバリデーションエラー"""
        reg = _make_registry(tmp_path)
        root = str(tmp_path / "stores" / "cas-store")
        reg.create_store("cas-store", root)
        result = reg.cas("cas-store", "bad key!", new_value="x")
        assert result["success"] is False
        assert result["error_type"] == "validation_error"


# ===================================================================
# list_keys (pagination)
# ===================================================================

class TestListKeys:

    @staticmethod
    def _populate(reg, store_id, keys, tmp_path):
        """CAS 経由でキーを投入する"""
        root = str(tmp_path / "stores" / store_id)
        reg.create_store(store_id, root)
        for k in keys:
            result = reg.cas(store_id, k, new_value="val")
            assert result["success"], f"Failed to populate key {k}: {result}"

    def test_list_all_keys(self, tmp_path):
        reg = _make_registry(tmp_path)
        self._populate(reg, "s1", ["a", "b", "c"], tmp_path)
        result = reg.list_keys("s1")
        assert result["success"] is True
        assert sorted(result["keys"]) == ["a", "b", "c"]
        assert result["has_more"] is False

    def test_list_with_prefix(self, tmp_path):
        reg = _make_registry(tmp_path)
        self._populate(reg, "s1", ["foo_1", "foo_2", "bar_1"], tmp_path)
        result = reg.list_keys("s1", prefix="foo")
        assert result["success"] is True
        assert sorted(result["keys"]) == ["foo_1", "foo_2"]

    def test_pagination(self, tmp_path):
        reg = _make_registry(tmp_path)
        self._populate(reg, "s1", [f"k{i:03d}" for i in range(10)], tmp_path)
        # First page
        r1 = reg.list_keys("s1", limit=3)
        assert r1["success"] is True
        assert len(r1["keys"]) == 3
        assert r1["has_more"] is True
        assert r1["next_cursor"] is not None
        # Second page
        r2 = reg.list_keys("s1", limit=3, cursor=r1["next_cursor"])
        assert r2["success"] is True
        assert len(r2["keys"]) == 3
        assert r2["has_more"] is True
        # Collect all pages
        all_keys = list(r1["keys"])
        cursor = r1["next_cursor"]
        while cursor:
            r = reg.list_keys("s1", limit=3, cursor=cursor)
            all_keys.extend(r["keys"])
            cursor = r["next_cursor"]
        assert len(all_keys) == 10
        assert len(set(all_keys)) == 10  # no duplicates

    def test_list_keys_store_not_found(self, tmp_path):
        reg = _make_registry(tmp_path)
        result = reg.list_keys("nonexistent")
        assert result["success"] is False

    def test_list_keys_empty_store(self, tmp_path):
        reg = _make_registry(tmp_path)
        reg.create_store("empty", str(tmp_path / "stores" / "empty"))
        result = reg.list_keys("empty")
        assert result["success"] is True
        assert result["keys"] == []


# ===================================================================
# batch_get
# ===================================================================

class TestBatchGet:

    @staticmethod
    def _populate(reg, store_id, data, tmp_path):
        """CAS 経由でキー/値ペアを投入する"""
        root = str(tmp_path / "stores" / store_id)
        reg.create_store(store_id, root)
        for k, v in data.items():
            result = reg.cas(store_id, k, new_value=v)
            assert result["success"], f"Failed to populate {k}: {result}"

    def test_batch_get_found(self, tmp_path):
        reg = _make_registry(tmp_path)
        self._populate(reg, "s1", {"a": 1, "b": 2, "c": 3}, tmp_path)
        result = reg.batch_get("s1", ["a", "c"])
        assert result["success"] is True
        assert result["results"]["a"] == 1
        assert result["results"]["c"] == 3
        assert result["found"] == 2
        assert result["not_found"] == 0

    def test_batch_get_partial(self, tmp_path):
        reg = _make_registry(tmp_path)
        self._populate(reg, "s1", {"a": 1}, tmp_path)
        result = reg.batch_get("s1", ["a", "missing"])
        assert result["found"] == 1
        assert result["not_found"] == 1
        assert result["results"]["missing"] is None

    def test_batch_get_store_not_found(self, tmp_path):
        reg = _make_registry(tmp_path)
        result = reg.batch_get("nonexistent", ["a"])
        assert result["success"] is False

    def test_batch_get_too_many_keys(self, tmp_path):
        reg = _make_registry(tmp_path)
        reg.create_store("s1", str(tmp_path / "stores" / "s1"))
        keys = [f"k{i}" for i in range(101)]
        result = reg.batch_get("s1", keys)
        assert result["success"] is False
        assert "Too many" in result["error"]

    def test_batch_get_empty_keys(self, tmp_path):
        reg = _make_registry(tmp_path)
        reg.create_store("s1", str(tmp_path / "stores" / "s1"))
        result = reg.batch_get("s1", [])
        assert result["success"] is False
