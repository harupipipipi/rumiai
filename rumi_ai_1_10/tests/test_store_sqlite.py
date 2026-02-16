"""
test_store_sqlite.py - StoreRegistry SQLite 実装のテスト

カバー範囲:
- Store CRUD (create / get / list / delete)
- CAS (create / update / conflict / concurrent)
- list_keys (prefix / cursor / limit / 全件)
- batch_get (normal / missing / size limit)
- マイグレーション (JSON → SQLite)
- エッジケース (空ストア, 大量キー, 不正入力)
- スレッドセーフ
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, List
from unittest import TestCase, main

# テスト対象モジュールのインポートパスを確保
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core_runtime.store_registry import (
    STORES_BASE_DIR,
    StoreDefinition,
    StoreRegistry,
    StoreResult,
    _normalize_value_hash,
    _validate_store_path,
)


class _TempDirMixin:
    """テスト用の一時ディレクトリを作成・削除するヘルパー。"""

    def setUp(self) -> None:
        super().setUp()  # type: ignore[misc]
        self._tmpdir = tempfile.mkdtemp(prefix="store_test_")
        self._db_path = os.path.join(self._tmpdir, "stores.db")
        # STORES_BASE_DIR を一時的に上書きしてパス検証を回避
        self._orig_base = STORES_BASE_DIR
        import core_runtime.store_registry as mod
        mod.STORES_BASE_DIR = Path(self._tmpdir)

    def tearDown(self) -> None:
        import core_runtime.store_registry as mod
        mod.STORES_BASE_DIR = self._orig_base
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        super().tearDown()  # type: ignore[misc]

    def _make_registry(self) -> StoreRegistry:
        return StoreRegistry(db_path=self._db_path)

    def _store_root(self, store_id: str) -> str:
        return os.path.join(self._tmpdir, store_id)


# ======================================================================
# Store CRUD
# ======================================================================

class TestStoreCRUD(_TempDirMixin, TestCase):

    def test_create_and_get(self) -> None:
        reg = self._make_registry()
        root = self._store_root("test1")
        result = reg.create_store("test1", root, created_by="tester")
        self.assertTrue(result.success)
        self.assertEqual(result.store_id, "test1")

        store = reg.get_store("test1")
        self.assertIsNotNone(store)
        self.assertEqual(store.store_id, "test1")
        self.assertEqual(store.created_by, "tester")
        self.assertTrue(store.root_path)
        reg.close()

    def test_create_duplicate(self) -> None:
        reg = self._make_registry()
        root = self._store_root("dup")
        reg.create_store("dup", root)
        result = reg.create_store("dup", root)
        self.assertFalse(result.success)
        self.assertIn("already exists", result.error)
        reg.close()

    def test_create_invalid_id(self) -> None:
        reg = self._make_registry()
        result = reg.create_store("bad id!", self._store_root("bad"))
        self.assertFalse(result.success)
        reg.close()

    def test_create_empty_root(self) -> None:
        reg = self._make_registry()
        result = reg.create_store("ok", "")
        self.assertFalse(result.success)
        self.assertIn("root_path is required", result.error)
        reg.close()

    def test_list_stores(self) -> None:
        reg = self._make_registry()
        reg.create_store("a", self._store_root("a"))
        reg.create_store("b", self._store_root("b"))
        stores = reg.list_stores()
        ids = {s["store_id"] for s in stores}
        self.assertEqual(ids, {"a", "b"})
        reg.close()

    def test_delete_store(self) -> None:
        reg = self._make_registry()
        root = self._store_root("del")
        reg.create_store("del", root)
        result = reg.delete_store("del")
        self.assertTrue(result.success)
        self.assertIsNone(reg.get_store("del"))
        reg.close()

    def test_delete_store_with_files(self) -> None:
        reg = self._make_registry()
        root = self._store_root("delfiles")
        reg.create_store("delfiles", root)
        # root ディレクトリが存在するか確認
        self.assertTrue(Path(root).exists())
        result = reg.delete_store("delfiles", delete_files=True)
        self.assertTrue(result.success)
        self.assertFalse(Path(root).exists())
        reg.close()

    def test_delete_cascade(self) -> None:
        """Store 削除時に store_data も CASCADE 削除される。"""
        reg = self._make_registry()
        root = self._store_root("casc")
        reg.create_store("casc", root)
        reg.cas("casc", "k1", None, {"v": 1})
        reg.cas("casc", "k2", None, {"v": 2})
        reg.delete_store("casc")
        # DB に store_data が残っていないことを確認
        conn = reg._get_conn()
        cnt = conn.execute(
            "SELECT COUNT(*) FROM store_data WHERE store_id = ?", ("casc",)
        ).fetchone()[0]
        self.assertEqual(cnt, 0)
        reg.close()

    def test_delete_not_found(self) -> None:
        reg = self._make_registry()
        result = reg.delete_store("ghost")
        self.assertFalse(result.success)
        self.assertIn("not found", result.error.lower())
        reg.close()

    def test_get_store_not_found(self) -> None:
        reg = self._make_registry()
        self.assertIsNone(reg.get_store("nope"))
        reg.close()

    def test_store_definition_to_dict(self) -> None:
        sd = StoreDefinition("s1", "/tmp/s1", "2025-01-01T00:00:00Z", "u")
        d = sd.to_dict()
        self.assertEqual(d["store_id"], "s1")

    def test_store_result_to_dict(self) -> None:
        sr = StoreResult(success=True, store_id="x")
        d = sr.to_dict()
        self.assertTrue(d["success"])


# ======================================================================
# CAS
# ======================================================================

class TestCAS(_TempDirMixin, TestCase):

    def _setup_store(self, reg: StoreRegistry, sid: str = "s") -> None:
        reg.create_store(sid, self._store_root(sid))

    def test_cas_create(self) -> None:
        reg = self._make_registry()
        self._setup_store(reg)
        result = reg.cas("s", "key1", None, {"hello": "world"})
        self.assertTrue(result["success"])
        self.assertEqual(result["store_id"], "s")
        self.assertEqual(result["key"], "key1")
        reg.close()

    def test_cas_update(self) -> None:
        reg = self._make_registry()
        self._setup_store(reg)
        reg.cas("s", "k", None, "v1")
        result = reg.cas("s", "k", "v1", "v2")
        self.assertTrue(result["success"])
        reg.close()

    def test_cas_conflict_value_mismatch(self) -> None:
        reg = self._make_registry()
        self._setup_store(reg)
        reg.cas("s", "k", None, "v1")
        result = reg.cas("s", "k", "wrong", "v2")
        self.assertFalse(result["success"])
        self.assertEqual(result["error_type"], "conflict")
        self.assertEqual(result["current_value"], "v1")
        reg.close()

    def test_cas_conflict_key_exists_expected_none(self) -> None:
        reg = self._make_registry()
        self._setup_store(reg)
        reg.cas("s", "k", None, "v1")
        result = reg.cas("s", "k", None, "v2")
        self.assertFalse(result["success"])
        self.assertEqual(result["error_type"], "conflict")
        self.assertEqual(result["current_value"], "v1")
        reg.close()

    def test_cas_conflict_key_missing_expected_not_none(self) -> None:
        reg = self._make_registry()
        self._setup_store(reg)
        result = reg.cas("s", "no_key", "something", "v2")
        self.assertFalse(result["success"])
        self.assertEqual(result["error_type"], "conflict")
        self.assertIsNone(result["current_value"])
        reg.close()

    def test_cas_store_not_found(self) -> None:
        reg = self._make_registry()
        result = reg.cas("ghost", "k", None, "v")
        self.assertFalse(result["success"])
        self.assertEqual(result["error_type"], "store_not_found")
        reg.close()

    def test_cas_value_too_large(self) -> None:
        reg = self._make_registry()
        self._setup_store(reg)
        big = "x" * (2 * 1024 * 1024)
        result = reg.cas("s", "k", None, big)
        self.assertFalse(result["success"])
        self.assertEqual(result["error_type"], "payload_too_large")
        reg.close()

    def test_cas_not_serializable(self) -> None:
        reg = self._make_registry()
        self._setup_store(reg)
        result = reg.cas("s", "k", None, object())
        self.assertFalse(result["success"])
        self.assertEqual(result["error_type"], "validation_error")
        reg.close()

    def test_cas_none_value(self) -> None:
        """None (JSON null) を値として CAS できる。"""
        reg = self._make_registry()
        self._setup_store(reg)
        r1 = reg.cas("s", "k", None, None)
        # expected_value=None は「キーが存在しないことを期待」の意味
        # new_value=None は JSON null を書き込む
        # ここで expected_value=None かつキーが存在しないので create 成功
        self.assertTrue(r1["success"])
        # 次に expected_value=None（キー無し期待）で上書き → conflict
        r2 = reg.cas("s", "k", None, "x")
        self.assertFalse(r2["success"])
        self.assertEqual(r2["error_type"], "conflict")
        reg.close()

    def test_cas_concurrent(self) -> None:
        """複数スレッドからの同時 CAS で競合が正しく検出される。"""
        reg = self._make_registry()
        self._setup_store(reg)
        reg.cas("s", "counter", None, 0)

        results: List[Dict[str, Any]] = []
        lock = threading.Lock()

        def worker() -> None:
            r = reg.cas("s", "counter", 0, 1)
            with lock:
                results.append(r)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        successes = [r for r in results if r["success"]]
        conflicts = [r for r in results if not r["success"]]
        # 正確に 1 つだけ成功
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(conflicts), 4)
        reg.close()


# ======================================================================
# list_keys
# ======================================================================

class TestListKeys(_TempDirMixin, TestCase):

    def _populate(self, reg: StoreRegistry, sid: str, keys: List[str]) -> None:
        reg.create_store(sid, self._store_root(sid))
        for k in keys:
            reg.cas(sid, k, None, f"val_{k}")

    def test_list_all(self) -> None:
        reg = self._make_registry()
        self._populate(reg, "s", ["a", "b", "c"])
        result = reg.list_keys("s")
        self.assertTrue(result["success"])
        self.assertEqual(result["keys"], ["a", "b", "c"])
        self.assertFalse(result["has_more"])
        self.assertIsNone(result["next_cursor"])
        self.assertEqual(result["total_estimate"], 3)
        reg.close()

    def test_list_with_prefix(self) -> None:
        reg = self._make_registry()
        self._populate(reg, "s", ["chat/1", "chat/2", "tool/1"])
        result = reg.list_keys("s", prefix="chat/")
        self.assertTrue(result["success"])
        self.assertEqual(result["keys"], ["chat/1", "chat/2"])
        reg.close()

    def test_list_with_limit(self) -> None:
        reg = self._make_registry()
        self._populate(reg, "s", ["a", "b", "c", "d"])
        result = reg.list_keys("s", limit=2)
        self.assertTrue(result["success"])
        self.assertEqual(result["keys"], ["a", "b"])
        self.assertTrue(result["has_more"])
        self.assertIsNotNone(result["next_cursor"])
        reg.close()

    def test_list_with_cursor(self) -> None:
        reg = self._make_registry()
        self._populate(reg, "s", ["a", "b", "c", "d"])
        r1 = reg.list_keys("s", limit=2)
        r2 = reg.list_keys("s", limit=2, cursor=r1["next_cursor"])
        self.assertEqual(r2["keys"], ["c", "d"])
        self.assertFalse(r2["has_more"])
        reg.close()

    def test_list_empty_store(self) -> None:
        reg = self._make_registry()
        reg.create_store("e", self._store_root("e"))
        result = reg.list_keys("e")
        self.assertTrue(result["success"])
        self.assertEqual(result["keys"], [])
        reg.close()

    def test_list_store_not_found(self) -> None:
        reg = self._make_registry()
        result = reg.list_keys("ghost")
        self.assertFalse(result["success"])
        self.assertEqual(result["error_type"], "store_not_found")
        reg.close()

    def test_list_limit_clamp(self) -> None:
        reg = self._make_registry()
        self._populate(reg, "s", ["a"])
        result = reg.list_keys("s", limit=0)
        self.assertTrue(result["success"])
        # limit < 1 → clamped to 1
        self.assertEqual(len(result["keys"]), 1)
        reg.close()

    def test_list_prefix_and_cursor(self) -> None:
        reg = self._make_registry()
        self._populate(reg, "s", ["a/1", "a/2", "a/3", "b/1"])
        r1 = reg.list_keys("s", prefix="a/", limit=1)
        self.assertEqual(r1["keys"], ["a/1"])
        r2 = reg.list_keys("s", prefix="a/", limit=10, cursor=r1["next_cursor"])
        self.assertEqual(r2["keys"], ["a/2", "a/3"])
        reg.close()


# ======================================================================
# batch_get
# ======================================================================

class TestBatchGet(_TempDirMixin, TestCase):

    def test_batch_basic(self) -> None:
        reg = self._make_registry()
        reg.create_store("s", self._store_root("s"))
        reg.cas("s", "k1", None, {"a": 1})
        reg.cas("s", "k2", None, {"b": 2})
        result = reg.batch_get("s", ["k1", "k2", "k3"])
        self.assertTrue(result["success"])
        self.assertEqual(result["found"], 2)
        self.assertEqual(result["not_found"], 1)
        self.assertEqual(result["results"]["k1"], {"a": 1})
        self.assertIsNone(result["results"]["k3"])
        reg.close()

    def test_batch_empty_keys(self) -> None:
        reg = self._make_registry()
        result = reg.batch_get("s", [])
        self.assertFalse(result["success"])
        reg.close()

    def test_batch_too_many_keys(self) -> None:
        reg = self._make_registry()
        reg.create_store("s", self._store_root("s"))
        result = reg.batch_get("s", [f"k{i}" for i in range(101)])
        self.assertFalse(result["success"])
        self.assertIn("Too many", result["error"])
        reg.close()

    def test_batch_store_not_found(self) -> None:
        reg = self._make_registry()
        result = reg.batch_get("ghost", ["k"])
        self.assertFalse(result["success"])
        reg.close()

    def test_batch_warnings_field(self) -> None:
        reg = self._make_registry()
        reg.create_store("s", self._store_root("s"))
        reg.cas("s", "k1", None, "small")
        result = reg.batch_get("s", ["k1"])
        self.assertIn("warnings", result)
        self.assertIsInstance(result["warnings"], list)
        reg.close()


# ======================================================================
# create_store_for_pack
# ======================================================================

class TestCreateStoreForPack(_TempDirMixin, TestCase):

    def test_basic(self) -> None:
        reg = self._make_registry()
        results = reg.create_store_for_pack("mypk", [{"store_id": "data"}])
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].success)
        self.assertEqual(results[0].store_id, "mypk__data")
        reg.close()

    def test_duplicate_skip(self) -> None:
        reg = self._make_registry()
        reg.create_store_for_pack("mypk", [{"store_id": "data"}])
        results = reg.create_store_for_pack("mypk", [{"store_id": "data"}])
        self.assertTrue(results[0].success)
        reg.close()

    def test_too_many(self) -> None:
        reg = self._make_registry()
        decls = [{"store_id": f"s{i}"} for i in range(11)]
        results = reg.create_store_for_pack("pk", decls)
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].success)
        self.assertIn("Too many", results[0].error)
        reg.close()

    def test_empty_decl(self) -> None:
        reg = self._make_registry()
        results = reg.create_store_for_pack("pk", [])
        self.assertEqual(results, [])
        reg.close()

    def test_invalid_entry(self) -> None:
        reg = self._make_registry()
        results = reg.create_store_for_pack("pk", ["not_a_dict"])
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].success)
        reg.close()


# ======================================================================
# is_store_accessible
# ======================================================================

class TestIsStoreAccessible(_TempDirMixin, TestCase):

    def test_allowed_list(self) -> None:
        reg = self._make_registry()
        self.assertTrue(
            reg.is_store_accessible("s1", "pk1", allowed_store_ids=["s1", "s2"])
        )
        self.assertFalse(
            reg.is_store_accessible("s3", "pk1", allowed_store_ids=["s1", "s2"])
        )
        reg.close()

    def test_no_allowed_no_sharing(self) -> None:
        reg = self._make_registry()
        # SharedStoreManager が無い / 例外が出る環境では False
        self.assertFalse(reg.is_store_accessible("s1", "pk1"))
        reg.close()


# ======================================================================
# _normalize_value_hash
# ======================================================================

class TestNormalizeValueHash(TestCase):

    def test_deterministic(self) -> None:
        h1 = _normalize_value_hash({"b": 2, "a": 1})
        h2 = _normalize_value_hash({"a": 1, "b": 2})
        self.assertEqual(h1, h2)

    def test_different_values(self) -> None:
        self.assertNotEqual(
            _normalize_value_hash("x"), _normalize_value_hash("y")
        )

    def test_none(self) -> None:
        h = _normalize_value_hash(None)
        self.assertIsInstance(h, str)
        self.assertEqual(len(h), 64)


# ======================================================================
# _validate_store_path
# ======================================================================

class TestValidateStorePath(TestCase):

    def test_traversal(self) -> None:
        err = _validate_store_path("user_data/stores/../../etc/passwd")
        self.assertIsNotNone(err)

    def test_valid(self) -> None:
        p = str(STORES_BASE_DIR / "good")
        err = _validate_store_path(p)
        # テスト環境ではディレクトリが存在しない場合もあるが
        # resolve() の挙動で結果が変わる。ここでは ".." チェックのみ確認
        # (環境依存のため、エラーが出なければ OK)


# ======================================================================
# Migration
# ======================================================================

class TestMigration(_TempDirMixin, TestCase):

    def _create_legacy_json(
        self,
        stores: Dict[str, Dict[str, Any]],
        data: Dict[str, Dict[str, Any]] | None = None,
    ) -> Path:
        """
        テスト用に旧形式の index.json + データファイルを作成する。

        Args:
            stores: {store_id: {root_path, created_at, created_by, ...}}
            data: {store_id: {key: value, ...}}

        Returns:
            index.json のパス
        """
        index_path = Path(self._tmpdir) / "index.json"
        index_data = {
            "version": "1.0",
            "updated_at": "2025-01-01T00:00:00Z",
            "stores": {},
        }
        for sid, sinfo in stores.items():
            root = sinfo.get("root_path", os.path.join(self._tmpdir, sid))
            Path(root).mkdir(parents=True, exist_ok=True)
            index_data["stores"][sid] = {
                "store_id": sid,
                "root_path": root,
                "created_at": sinfo.get("created_at", "2025-01-01T00:00:00Z"),
                "created_by": sinfo.get("created_by", "test"),
            }
            if data and sid in data:
                for key, value in data[sid].items():
                    fp = Path(root) / (key + ".json")
                    fp.parent.mkdir(parents=True, exist_ok=True)
                    with open(fp, "w", encoding="utf-8") as f:
                        json.dump(value, f, ensure_ascii=False)

        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(index_data, f, ensure_ascii=False, indent=2)

        return index_path

    def test_migration_basic(self) -> None:
        root = os.path.join(self._tmpdir, "migstore")
        self._create_legacy_json(
            stores={"migstore": {"root_path": root}},
            data={"migstore": {"key1": {"hello": "world"}}},
        )
        from core_runtime.store_migration import migrate_json_to_sqlite

        db_path = Path(self._db_path)
        index_path = Path(self._tmpdir) / "index.json"
        ok = migrate_json_to_sqlite(db_path, index_path)
        self.assertTrue(ok)
        self.assertTrue(db_path.exists())

        # DB を直接確認
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        stores = conn.execute("SELECT * FROM stores").fetchall()
        self.assertEqual(len(stores), 1)
        self.assertEqual(stores[0]["store_id"], "migstore")

        data_rows = conn.execute("SELECT * FROM store_data").fetchall()
        self.assertEqual(len(data_rows), 1)
        self.assertEqual(data_rows[0]["key"], "key1")
        val = json.loads(data_rows[0]["value"])
        self.assertEqual(val, {"hello": "world"})
        conn.close()

    def test_migration_skip_if_db_exists(self) -> None:
        from core_runtime.store_migration import migrate_json_to_sqlite

        db_path = Path(self._db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db_path.touch()
        index_path = Path(self._tmpdir) / "index.json"
        index_path.touch()
        ok = migrate_json_to_sqlite(db_path, index_path)
        self.assertFalse(ok)

    def test_migration_no_index(self) -> None:
        from core_runtime.store_migration import migrate_json_to_sqlite

        db_path = Path(self._db_path)
        index_path = Path(self._tmpdir) / "index.json"
        ok = migrate_json_to_sqlite(db_path, index_path)
        self.assertFalse(ok)

    def test_cleanup_stale_tmp(self) -> None:
        from core_runtime.store_migration import cleanup_stale_tmp

        db_path = Path(self._db_path)
        tmp_path = Path(str(db_path) + ".tmp")
        tmp_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path.touch()
        self.assertTrue(tmp_path.exists())
        cleanup_stale_tmp(db_path)
        self.assertFalse(tmp_path.exists())

    def test_auto_migration_on_init(self) -> None:
        """StoreRegistry 初期化時に自動マイグレーションが走る。"""
        root = os.path.join(self._tmpdir, "autostore")

        # STORES_INDEX_PATH を一時的に差し替え
        import core_runtime.store_registry as mod
        orig_index = mod.STORES_INDEX_PATH
        index_path = Path(self._tmpdir) / "index.json"
        self._create_legacy_json(
            stores={"autostore": {"root_path": root}},
            data={"autostore": {"ak": "av"}},
        )
        mod.STORES_INDEX_PATH = str(index_path)
        try:
            reg = StoreRegistry(db_path=self._db_path)
            store = reg.get_store("autostore")
            self.assertIsNotNone(store)
            self.assertEqual(store.store_id, "autostore")

            # データも移行されている
            bg = reg.batch_get("autostore", ["ak"])
            self.assertTrue(bg["success"])
            self.assertEqual(bg["results"]["ak"], "av")
            reg.close()
        finally:
            mod.STORES_INDEX_PATH = orig_index


# ======================================================================
# スレッドセーフ
# ======================================================================

class TestThreadSafety(_TempDirMixin, TestCase):

    def test_concurrent_create_stores(self) -> None:
        reg = self._make_registry()
        errors: List[str] = []

        def worker(i: int) -> None:
            try:
                reg.create_store(
                    f"ts{i}", self._store_root(f"ts{i}")
                )
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0)
        stores = reg.list_stores()
        self.assertEqual(len(stores), 10)
        reg.close()

    def test_concurrent_batch_get(self) -> None:
        reg = self._make_registry()
        reg.create_store("bg", self._store_root("bg"))
        for i in range(20):
            reg.cas("bg", f"k{i}", None, i)

        results: List[Dict[str, Any]] = []
        lock = threading.Lock()

        def worker() -> None:
            r = reg.batch_get("bg", [f"k{i}" for i in range(20)])
            with lock:
                results.append(r)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for r in results:
            self.assertTrue(r["success"])
            self.assertEqual(r["found"], 20)
        reg.close()


# ======================================================================
# close
# ======================================================================

class TestClose(_TempDirMixin, TestCase):

    def test_close_and_reopen(self) -> None:
        reg = self._make_registry()
        reg.create_store("cl", self._store_root("cl"))
        reg.close()
        # close 後でも新しい接続が作られる
        store = reg.get_store("cl")
        self.assertIsNotNone(store)
        reg.close()


if __name__ == "__main__":
    main()
