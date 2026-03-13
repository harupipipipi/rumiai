"""
test_phase_a.py - Phase A: FunctionEntry 拡張のテスト

対象: core_runtime/function_registry.py (Phase A 変更分)
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core_runtime.function_registry import (
    FunctionEntry,
    FunctionRegistry,
    ManifestRegistry,
    _PROTECTED_VOCAB_PREFIXES,
    handler_to_manifest_adapter,
)


# ===================================================================
# Wave A-1: FunctionEntry フィールド追加
# ===================================================================


class TestFunctionEntryNewFields:

    def test_function_entry_new_fields_default_none(self):
        """FunctionEntry を既存フィールドのみで作成した場合、4 新フィールドが全て None"""
        entry = FunctionEntry(function_id="fn1", pack_id="pk1")
        assert entry.entrypoint is None
        assert entry.risk is None
        assert entry.grant_config is None
        assert entry.vocab_aliases is None

    def test_function_entry_new_fields_set(self):
        """FunctionEntry を全フィールド指定で作成した場合、4 新フィールドが正しく設定される"""
        entry = FunctionEntry(
            function_id="fn1",
            pack_id="pk1",
            entrypoint="handler.py",
            risk="high",
            grant_config={"network": True},
            vocab_aliases=["store.get", "data.read"],
        )
        assert entry.entrypoint == "handler.py"
        assert entry.risk == "high"
        assert entry.grant_config == {"network": True}
        assert entry.vocab_aliases == ["store.get", "data.read"]

    def test_entry_from_kwargs_new_fields(self, tmp_path):
        """_entry_from_kwargs が 4 新フィールドを kwargs から受け取れる"""
        func_dir = tmp_path / "func"
        func_dir.mkdir()
        manifest = {
            "description": "test",
            "entrypoint": "run.py",
            "risk": "medium",
            "grant_config": {"fs": False},
            "vocab_aliases": ["perm.execute"],
        }
        entry = FunctionRegistry._entry_from_kwargs(
            pack_id="pk1",
            function_id="fn1",
            manifest=manifest,
            function_dir=str(func_dir),
        )
        assert entry.entrypoint == "run.py"
        assert entry.risk == "medium"
        assert entry.grant_config == {"fs": False}
        assert entry.vocab_aliases == ["perm.execute"]

    def test_entry_from_kwargs_new_fields_default(self, tmp_path):
        """_entry_from_kwargs に新フィールドを渡さない場合、デフォルト None になる"""
        func_dir = tmp_path / "func"
        func_dir.mkdir()
        manifest = {"description": "test"}
        entry = FunctionRegistry._entry_from_kwargs(
            pack_id="pk1",
            function_id="fn1",
            manifest=manifest,
            function_dir=str(func_dir),
        )
        assert entry.entrypoint is None
        assert entry.risk is None
        assert entry.grant_config is None
        assert entry.vocab_aliases is None


# ===================================================================
# Wave A-2: FunctionRegistry メソッド追加 + vocab_aliases 管理
# ===================================================================


class TestVocabAliasRegistration:

    def test_vocab_alias_register_and_resolve(self):
        """register() で vocab_aliases 付きエントリを登録し、resolve_by_alias() で解決できる"""
        reg = FunctionRegistry()
        entry = FunctionEntry(
            function_id="fn1",
            pack_id="pk1",
            vocab_aliases=["store.get"],
        )
        assert reg.register(entry) is True
        resolved = reg.resolve_by_alias("store.get")
        assert resolved is not None
        assert resolved.qualified_name == "pk1:fn1"

    def test_vocab_alias_not_found(self):
        """存在しない alias で resolve_by_alias() が None を返す"""
        reg = FunctionRegistry()
        assert reg.resolve_by_alias("nonexistent.alias") is None

    def test_protected_vocab_prefix_rejected(self):
        """非 core pack から保護プレフィックス alias を登録しようとすると alias が拒否される"""
        reg = FunctionRegistry()
        entry = FunctionEntry(
            function_id="fn1",
            pack_id="external.pack",
            vocab_aliases=["system.admin", "safe.alias"],
        )
        assert reg.register(entry) is True
        # 関数自体は登録されている
        assert reg.get("external.pack:fn1") is not None
        # 保護プレフィックスの alias は拒否されている
        assert reg.resolve_by_alias("system.admin") is None
        # 保護でない alias は登録されている
        assert reg.resolve_by_alias("safe.alias") is not None

    def test_protected_vocab_prefix_core_pack_allowed(self):
        """core pack からは保護プレフィックス alias を登録できる"""
        reg = FunctionRegistry()
        entry = FunctionEntry(
            function_id="fn1",
            pack_id="core.system",
            vocab_aliases=["system.admin", "kernel.boot"],
        )
        assert reg.register(entry) is True
        assert reg.resolve_by_alias("system.admin") is not None
        assert reg.resolve_by_alias("kernel.boot") is not None

    def test_vocab_alias_duplicate_rejected(self):
        """既に別の function にマッピングされている alias を登録しようとすると拒否される"""
        reg = FunctionRegistry()
        entry1 = FunctionEntry(
            function_id="fn1",
            pack_id="pk1",
            vocab_aliases=["shared.alias"],
        )
        entry2 = FunctionEntry(
            function_id="fn2",
            pack_id="pk1",
            vocab_aliases=["shared.alias"],
        )
        assert reg.register(entry1) is True
        assert reg.register(entry2) is True
        # alias は最初の登録者のまま
        resolved = reg.resolve_by_alias("shared.alias")
        assert resolved is not None
        assert resolved.qualified_name == "pk1:fn1"

    def test_unregister_pack_clears_aliases(self):
        """unregister_pack() で pack の function と共に alias も削除される"""
        reg = FunctionRegistry()
        entry = FunctionEntry(
            function_id="fn1",
            pack_id="pk1",
            vocab_aliases=["my.alias"],
        )
        reg.register(entry)
        assert reg.resolve_by_alias("my.alias") is not None
        reg.unregister_pack("pk1")
        assert reg.resolve_by_alias("my.alias") is None

    def test_clear_clears_aliases(self):
        """clear() で alias も全削除される"""
        reg = FunctionRegistry()
        entry = FunctionEntry(
            function_id="fn1",
            pack_id="pk1",
            vocab_aliases=["my.alias"],
        )
        reg.register(entry)
        assert reg.resolve_by_alias("my.alias") is not None
        reg.clear()
        assert reg.resolve_by_alias("my.alias") is None


class TestSearchUnified:

    def test_search_unified_by_alias(self):
        """search_unified() が alias 完全一致で function を返す"""
        reg = FunctionRegistry()
        entry = FunctionEntry(
            function_id="fn1",
            pack_id="pk1",
            vocab_aliases=["store.get"],
        )
        reg.register(entry)
        results = reg.search_unified("store.get")
        assert len(results) >= 1
        assert results[0].qualified_name == "pk1:fn1"

    def test_search_unified_by_tag(self):
        """search_unified() が tag 一致の結果を含む"""
        reg = FunctionRegistry()
        entry = FunctionEntry(
            function_id="fn1",
            pack_id="pk1",
            tags=["storage"],
        )
        reg.register(entry)
        results = reg.search_unified("storage")
        assert any(e.qualified_name == "pk1:fn1" for e in results)

    def test_search_unified_dedup(self):
        """search_unified() が重複する結果を排除する"""
        reg = FunctionRegistry()
        # function_id と tag と alias が全て同じクエリにマッチするエントリ
        entry = FunctionEntry(
            function_id="myquery",
            pack_id="pk1",
            tags=["myquery"],
            vocab_aliases=["myquery"],
        )
        reg.register(entry)
        results = reg.search_unified("myquery")
        qnames = [e.qualified_name for e in results]
        # 重複がないことを確認
        assert len(qnames) == len(set(qnames))
        assert "pk1:myquery" in qnames

    def test_search_unified_limit(self):
        """search_unified() が limit パラメータで結果数を制限する"""
        reg = FunctionRegistry()
        for i in range(10):
            entry = FunctionEntry(
                function_id=f"func_{i}",
                pack_id="pk1",
                description="common description for fuzzy match",
            )
            reg.register(entry)
        results = reg.search_unified("common description", limit=3)
        assert len(results) <= 3


# ===================================================================
# Wave A-3: handler_to_manifest_adapter + ManifestRegistry alias
# ===================================================================


class TestHandlerToManifestAdapter:

    def test_handler_to_manifest_adapter_basic(self, tmp_path):
        """標準的な handler.json dict を変換し、正しい kwargs dict が返る"""
        handler_dir = tmp_path / "handler"
        handler_dir.mkdir()
        (handler_dir / "handler.py").write_text("# handler", encoding="utf-8")

        handler_json = {
            "description": "A test handler",
            "permission_id": "store.get",
            "entrypoint": "handler.py",
            "risk": "low",
            "input_schema": {"type": "object"},
            "output_schema": {"type": "string"},
            "grant_config_schema": {"network": True},
            "tags": ["storage"],
            "requires": ["fs"],
        }
        result = handler_to_manifest_adapter(
            handler_json, str(handler_dir), "pk1", "fn1"
        )
        assert result["pack_id"] == "pk1"
        assert result["function_id"] == "fn1"
        assert result["function_dir"] == str(handler_dir)
        m = result["manifest"]
        assert m["description"] == "A test handler"
        assert m["entrypoint"] == "handler.py"
        assert m["risk"] == "low"
        assert m["input_schema"] == {"type": "object"}
        assert m["output_schema"] == {"type": "string"}
        assert m["grant_config"] == {"network": True}
        assert m["vocab_aliases"] == ["store.get"]
        assert m["runtime"] == "python"
        assert m["host_execution"] is True
        assert m["tags"] == ["storage"]
        assert m["requires"] == ["fs"]

    def test_handler_to_manifest_adapter_minimal(self, tmp_path):
        """最小限のフィールドの handler.json でも動作する"""
        handler_dir = tmp_path / "handler"
        handler_dir.mkdir()

        handler_json = {
            "description": "minimal",
            "permission_id": "store.get",
        }
        result = handler_to_manifest_adapter(
            handler_json, str(handler_dir), "pk1", "fn1"
        )
        m = result["manifest"]
        assert m["description"] == "minimal"
        assert m["entrypoint"] == "handler.py"  # default
        assert m["risk"] is None
        assert m["grant_config"] is None
        assert m["input_schema"] == {}
        assert m["output_schema"] == {}

    def test_handler_to_manifest_adapter_vocab_aliases(self, tmp_path):
        """permission_id が vocab_aliases リストに変換される"""
        handler_dir = tmp_path / "handler"
        handler_dir.mkdir()

        handler_json = {
            "description": "d",
            "permission_id": "store.get",
        }
        result = handler_to_manifest_adapter(
            handler_json, str(handler_dir), "pk1", "fn1"
        )
        assert result["manifest"]["vocab_aliases"] == ["store.get"]


class TestManifestRegistryAlias:

    def test_manifest_registry_is_function_registry(self):
        """ManifestRegistry is FunctionRegistry が True である"""
        assert ManifestRegistry is FunctionRegistry


# ===================================================================
# Phase A Spec Tests (12 required tests)
# ===================================================================


class TestPhaseASpec:
    """仕様書で要求されている 12 個のテスト"""

    # 1. FunctionEntry に新フィールドが存在し、デフォルト値が正しいことを確認
    def test_new_fields_exist_with_defaults(self):
        entry = FunctionEntry(function_id="fn1", pack_id="pk1")
        assert entry.permission_id is None
        assert entry.handler_py_sha256 is None
        assert entry.is_builtin is False
        assert entry.grant_config_schema is None
        assert entry.calling_convention is None
        # 既存 Phase A フィールドもデフォルト確認
        assert entry.entrypoint is None
        assert entry.risk is None

    # 2. 新フィールドを指定して register() -> get() で取得 -> 全フィールドが保持されていることを確認
    def test_register_with_new_fields_preserved(self):
        reg = FunctionRegistry()
        entry = FunctionEntry(
            function_id="fn1",
            pack_id="pk1",
            description="test function",
            permission_id="perm.test",
            handler_py_sha256="abc123hash",
            is_builtin=True,
            grant_config_schema={"network": True},
            calling_convention="kernel",
            entrypoint="handler.py",
            risk="high",
        )
        reg.register(entry)
        got = reg.get("pk1:fn1")
        assert got is not None
        assert got.permission_id == "perm.test"
        assert got.handler_py_sha256 == "abc123hash"
        assert got.is_builtin is True
        assert got.grant_config_schema == {"network": True}
        assert got.calling_convention == "kernel"
        assert got.entrypoint == "handler.py"
        assert got.risk == "high"

    # 3. 新フィールドを指定せずに register() -> 既存の動作が壊れていないことを確認
    def test_register_without_new_fields_backward_compat(self):
        reg = FunctionRegistry()
        entry = FunctionEntry(
            function_id="fn1",
            pack_id="pk1",
            description="basic function",
            tags=["basic"],
        )
        assert reg.register(entry) is True
        got = reg.get("pk1:fn1")
        assert got is not None
        assert got.function_id == "fn1"
        assert got.pack_id == "pk1"
        assert got.description == "basic function"
        assert got.tags == ["basic"]
        # 新フィールドはデフォルト
        assert got.permission_id is None
        assert got.is_builtin is False
        assert got.calling_convention is None

    # 4. register_kernel_function() で登録 -> get() で取得 -> pack_id="kernel", calling_convention="kernel", is_builtin=True
    def test_register_kernel_function(self):
        reg = FunctionRegistry()
        manifest = {
            "description": "kernel func",
            "permission_id": "kernel.test",
            "input_schema": {"type": "object"},
        }
        reg.register_kernel_function("kfn1", manifest)
        got = reg.get("kernel:kfn1")
        assert got is not None
        assert got.pack_id == "kernel"
        assert got.function_id == "kfn1"
        assert got.calling_convention == "kernel"
        assert got.is_builtin is True
        assert got.description == "kernel func"
        assert got.permission_id == "kernel.test"
        assert got.input_schema == {"type": "object"}

    # 5. permission_id 付きで register() -> get_by_permission_id() で取得できること
    def test_get_by_permission_id_found(self):
        reg = FunctionRegistry()
        entry = FunctionEntry(
            function_id="fn1",
            pack_id="pk1",
            permission_id="perm.read",
        )
        reg.register(entry)
        got = reg.get_by_permission_id("perm.read")
        assert got is not None
        assert got.qualified_name == "pk1:fn1"
        assert got.permission_id == "perm.read"

    # 6. permission_id なしで register() -> get_by_permission_id() で None が返ること
    def test_get_by_permission_id_none(self):
        reg = FunctionRegistry()
        entry = FunctionEntry(
            function_id="fn1",
            pack_id="pk1",
        )
        reg.register(entry)
        got = reg.get_by_permission_id("perm.read")
        assert got is None

    # 7. unregister_pack() -> get_by_permission_id() で None が返ること（インデックス削除の確認）
    def test_unregister_pack_clears_permission_id_index(self):
        reg = FunctionRegistry()
        entry = FunctionEntry(
            function_id="fn1",
            pack_id="pk1",
            permission_id="perm.write",
        )
        reg.register(entry)
        assert reg.get_by_permission_id("perm.write") is not None
        reg.unregister_pack("pk1")
        assert reg.get_by_permission_id("perm.write") is None

    # 8. search_unified() テキスト検索: description にマッチする entry が返ること
    def test_search_unified_text_match(self):
        reg = FunctionRegistry()
        entry1 = FunctionEntry(
            function_id="fn1",
            pack_id="pk1",
            description="file storage manager",
        )
        entry2 = FunctionEntry(
            function_id="fn2",
            pack_id="pk1",
            description="network handler",
        )
        reg.register(entry1)
        reg.register(entry2)
        results = reg.search_unified("file storage")
        qnames = [e.qualified_name for e in results]
        assert "pk1:fn1" in qnames

    # 9. search_unified() フィルタ: calling_convention="kernel" で kernel function のみ返ること
    def test_search_unified_filter_calling_convention(self):
        reg = FunctionRegistry()
        reg.register_kernel_function("kfn1", {"description": "kernel func"})
        entry2 = FunctionEntry(
            function_id="fn2",
            pack_id="pk2",
            description="normal func",
            calling_convention="subprocess",
        )
        reg.register(entry2)
        results = reg.search_unified(
            filters={"calling_convention": "kernel"},
        )
        assert len(results) >= 1
        for e in results:
            assert e.calling_convention == "kernel"

    # 10. search_unified() フィルタ: is_builtin=True でビルトインのみ返ること
    def test_search_unified_filter_is_builtin(self):
        reg = FunctionRegistry()
        reg.register_kernel_function("kfn1", {"description": "builtin"})
        entry2 = FunctionEntry(
            function_id="fn2",
            pack_id="pk2",
            description="not builtin",
            is_builtin=False,
        )
        reg.register(entry2)
        results = reg.search_unified(
            filters={"is_builtin": True},
        )
        assert len(results) >= 1
        for e in results:
            assert e.is_builtin is True

    # 11. search_unified() 複合: query + filters の組み合わせ
    def test_search_unified_combined_query_and_filters(self):
        reg = FunctionRegistry()
        reg.register_kernel_function("kfn1", {"description": "kernel data processor"})
        entry2 = FunctionEntry(
            function_id="fn2",
            pack_id="pk2",
            description="data processor non-kernel",
            calling_convention="subprocess",
        )
        reg.register(entry2)
        # query で "data processor" にマッチするもの + calling_convention="kernel" でフィルタ
        results = reg.search_unified(
            query="data processor",
            filters={"calling_convention": "kernel"},
        )
        for e in results:
            assert e.calling_convention == "kernel"

    # 12. clear() 後に _permission_id_index も空であること
    def test_clear_clears_permission_id_index(self):
        reg = FunctionRegistry()
        entry = FunctionEntry(
            function_id="fn1",
            pack_id="pk1",
            permission_id="perm.admin",
        )
        reg.register(entry)
        assert reg.get_by_permission_id("perm.admin") is not None
        reg.clear()
        assert reg.get_by_permission_id("perm.admin") is None
        assert len(reg._permission_id_index) == 0
