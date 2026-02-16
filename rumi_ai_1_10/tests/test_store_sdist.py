"""
test_store_sdist.py - Store audit (I-1) + CAS None semantics (I-5) テスト
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def store_registry(tmp_path, monkeypatch):
    """tmp_path ベースの StoreRegistry を作成する。"""
    import core_runtime.store_registry as sr_mod

    stores_base = tmp_path / "stores"
    stores_base.mkdir()

    monkeypatch.setattr(sr_mod, "STORES_BASE_DIR", stores_base)
    monkeypatch.setattr(sr_mod, "STORES_DB_PATH", str(stores_base / "stores.db"))
    monkeypatch.setattr(sr_mod, "STORES_INDEX_PATH", str(stores_base / "index.json"))

    registry = sr_mod.StoreRegistry(db_path=str(stores_base / "stores.db"))
    yield registry
    registry.close()


@pytest.fixture
def populated_store(store_registry, tmp_path):
    """3 キーが入ったストアを作成する。"""
    import core_runtime.store_registry as sr_mod

    stores_base = tmp_path / "stores"
    store_id = "test-store"
    root_path = str(stores_base / store_id)

    result = store_registry.create_store(
        store_id=store_id,
        root_path=root_path,
    )
    assert result.success, f"create_store failed: {result.error}"

    # キー1: 短い値
    r1 = store_registry.cas(store_id, "key1", new_value="hello")
    assert r1["success"], f"cas key1 failed: {r1}"

    # キー2: 中くらいの値
    r2 = store_registry.cas(store_id, "key2", new_value={"data": "x" * 100})
    assert r2["success"], f"cas key2 failed: {r2}"

    # キー3: 大きい値
    r3 = store_registry.cas(store_id, "key3", new_value=list(range(500)))
    assert r3["success"], f"cas key3 failed: {r3}"

    return store_id


# ---------------------------------------------------------------------------
# I-1: audit_store_usage テスト
# ---------------------------------------------------------------------------

class TestAuditStoreUsage:
    """I-1: sdist 監査テスト"""

    def test_audit_store_usage_basic(self, store_registry, populated_store):
        """3キー作成後にサイズ集計が正しく行われること。"""
        store_id = populated_store
        result = store_registry.audit_store_usage(store_id)

        assert result["store_id"] == store_id
        assert result["key_count"] == 3
        assert result["total_size_bytes"] > 0
        assert result["largest_key"] in ("key1", "key2", "key3")
        assert result["largest_size_bytes"] > 0
        assert result["largest_size_bytes"] <= result["total_size_bytes"]

        # largest_size_bytes は key3 (list(range(500))) が最大のはず
        # JSON: [0,1,2,...,499] → 各要素が可変長
        assert result["largest_key"] == "key3"

    def test_audit_store_usage_empty(self, store_registry, tmp_path):
        """空ストアで key_count=0 が返ること。"""
        import core_runtime.store_registry as sr_mod

        stores_base = tmp_path / "stores"
        store_id = "empty-store"
        root_path = str(stores_base / store_id)

        result = store_registry.create_store(
            store_id=store_id,
            root_path=root_path,
        )
        assert result.success

        audit = store_registry.audit_store_usage(store_id)
        assert audit["store_id"] == store_id
        assert audit["key_count"] == 0
        assert audit["total_size_bytes"] == 0
        assert audit["largest_key"] == ""
        assert audit["largest_size_bytes"] == 0

    def test_audit_store_not_found(self, store_registry):
        """存在しないストアにはエラーを返すこと。"""
        result = store_registry.audit_store_usage("nonexistent")
        assert result["success"] is False
        assert "not found" in result["error"].lower()


# ---------------------------------------------------------------------------
# I-5: CAS None vs _EXPECT_MISSING テスト
# ---------------------------------------------------------------------------

class TestCasNoneSemantics:
    """I-5: CAS None セマンティクス改善テスト"""

    def test_cas_none_vs_expect_missing(self, store_registry, tmp_path):
        """
        None と _EXPECT_MISSING の区別を検証する。

        - expected_value 省略 (= _EXPECT_MISSING): キー不存在を期待
        - expected_value=None: JSON null を期待
        """
        import core_runtime.store_registry as sr_mod

        stores_base = tmp_path / "stores"
        store_id = "cas-test"
        root_path = str(stores_base / store_id)

        r = store_registry.create_store(store_id=store_id, root_path=root_path)
        assert r.success

        # --- 1. expected_value 省略でキー新規作成 ---
        r1 = store_registry.cas(store_id, "k1", new_value="first")
        assert r1["success"] is True

        # --- 2. expected_value 省略で既存キーに書こうとする → conflict ---
        r2 = store_registry.cas(store_id, "k1", new_value="second")
        assert r2["success"] is False
        assert r2["error_type"] == "conflict"

        # --- 3. expected_value=None でキーが存在しない → conflict ---
        r3 = store_registry.cas(
            store_id, "k_not_exist", expected_value=None, new_value="x"
        )
        assert r3["success"] is False
        assert r3["error_type"] == "conflict"

        # --- 4. None 値をストアに格納 ---
        r4 = store_registry.cas(store_id, "k_null", new_value=None)
        assert r4["success"] is True

        # --- 5. expected_value=None で JSON null を期待 → 成功 ---
        r5 = store_registry.cas(
            store_id, "k_null", expected_value=None, new_value="replaced"
        )
        assert r5["success"] is True

        # --- 6. expected_value=None で値が null でない → conflict ---
        r6 = store_registry.cas(
            store_id, "k1", expected_value=None, new_value="nope"
        )
        assert r6["success"] is False
        assert r6["error_type"] == "conflict"

        # --- 7. _EXPECT_MISSING sentinel を直接使用 ---
        r7 = store_registry.cas(
            store_id, "k_new",
            expected_value=sr_mod._EXPECT_MISSING,
            new_value="created",
        )
        assert r7["success"] is True

        # --- 8. _EXPECT_MISSING で既存キー → conflict ---
        r8 = store_registry.cas(
            store_id, "k_new",
            expected_value=sr_mod._EXPECT_MISSING,
            new_value="again",
        )
        assert r8["success"] is False
        assert r8["error_type"] == "conflict"
