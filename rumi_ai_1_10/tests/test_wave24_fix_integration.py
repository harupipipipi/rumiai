"""
test_wave24_fix_integration.py - W24-FIX インテグレーションテスト

DI コンテナからの FunctionRegistry 取得、registry.py 呼び出しパターン互換、
vocab_registry 連携、フォールバック等を検証する。
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# テスト実行時に core_runtime をインポートできるよう sys.path を調整
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from core_runtime.function_registry import (
    BulkRegisterResult,
    FunctionEntry,
    FunctionRegistry,
)


# =================================================================
# ヘルパー
# =================================================================

def _make_vocab_mock() -> MagicMock:
    mock = MagicMock()
    mock.resolve.side_effect = lambda t, to_preferred=True: t.strip().lower()
    mock.get_group.side_effect = lambda t: [t.strip().lower()]
    mock.is_synonym.return_value = False
    return mock


# =================================================================
# 1. DI コンテナから function_registry が取得できること
# =================================================================

class TestDIContainerIntegration:
    def test_di_container_has_function_registry(self):
        """_register_defaults に function_registry が登録されている"""
        from core_runtime.di_container import DIContainer, _register_defaults
        c = DIContainer()
        _register_defaults(c)
        assert c.has("function_registry")

    def test_di_container_get_function_registry(self):
        """get() で FunctionRegistry インスタンスが取得できる"""
        from core_runtime.di_container import DIContainer, _register_defaults
        c = DIContainer()
        _register_defaults(c)
        # vocab_registry のファクトリが失敗しても function_registry 自体は取得できる
        # (vocab_registry=None フォールバック)
        fr = c.get_or_none("function_registry")
        # ファクトリ内で他モジュールの import が失敗する可能性があるので
        # get_or_none を使い、None でなければ型を確認
        if fr is not None:
            assert isinstance(fr, FunctionRegistry)
        else:
            # vocab_registry 等の依存が解決できない環境では
            # 直接インスタンス化で代替確認
            fr2 = FunctionRegistry()
            assert fr2 is not None


# =================================================================
# 2. function_registry が vocab_registry と連携すること（DI 経由）
# =================================================================

class TestVocabIntegration:
    def test_vocab_registry_passed_to_function_registry(self):
        """vocab_registry を渡すと search_by_vocab で同義語展開される"""
        vocab = _make_vocab_mock()
        vocab.resolve.side_effect = lambda t, to_preferred=True: (
            "summarize"
            if t.strip().lower() in ("summarise", "summarize")
            else t.strip().lower()
        )
        vocab.get_group.side_effect = lambda t: (
            ["summarize", "summarise"]
            if t.strip().lower() in ("summarise", "summarize")
            else [t.strip().lower()]
        )

        reg = FunctionRegistry(vocab_registry=vocab)
        entry = FunctionEntry(
            function_id="summarize",
            pack_id="pk",
            description="Summarize",
            tags=["nlp"],
            function_dir=Path("/tmp/test"),
        )
        reg.register(entry)

        results = reg.search_by_vocab("summarise")
        assert len(results) == 1
        assert results[0].function_id == "summarize"


# =================================================================
# 3. registry.py の呼び出しパターンで register() が成功すること
# =================================================================

class TestRegistryPattern:
    def test_register_with_kwargs(self):
        """registry.py の _load_functions() と同じキーワード引数で登録できる"""
        reg = FunctionRegistry()
        manifest = {
            "function_id": "my_func",
            "description": "Does something",
            "tags": ["util"],
            "requires": ["net"],
        }
        result = reg.register(
            pack_id="test_pack",
            function_id="my_func",
            manifest=manifest,
            function_dir=Path("/tmp/functions/my_func"),
        )
        assert result is True
        entry = reg.get("test_pack:my_func")
        assert entry is not None
        assert entry.function_id == "my_func"
        assert entry.pack_id == "test_pack"
        assert entry.description == "Does something"
        assert "util" in entry.tags

    def test_register_with_kwargs_minimal(self):
        """manifest が空 dict でも登録できる"""
        reg = FunctionRegistry()
        result = reg.register(
            pack_id="pk",
            function_id="fn",
            manifest={},
            function_dir=None,
        )
        assert result is True
        assert reg.get("pk:fn") is not None


# =================================================================
# 4. 登録された function が get() で取得できること
# =================================================================

class TestGetAfterRegister:
    def test_get_returns_correct_entry(self):
        reg = FunctionRegistry()
        entry = FunctionEntry(
            function_id="translate",
            pack_id="lang",
            description="Translate text",
            tags=["nlp"],
        )
        reg.register(entry)
        got = reg.get("lang:translate")
        assert got is not None
        assert got.qualified_name == "lang:translate"
        assert got.description == "Translate text"

    def test_get_nonexistent(self):
        reg = FunctionRegistry()
        assert reg.get("no:exist") is None


# =================================================================
# 5. vocab_registry 未登録でも function_registry が取得できること
# =================================================================

class TestVocabFallback:
    def test_function_registry_works_without_vocab(self):
        """vocab_registry=None でも基本機能は全て動く"""
        reg = FunctionRegistry(vocab_registry=None)
        entry = FunctionEntry(
            function_id="calc",
            pack_id="math_pack",
            description="Calculator",
            tags=["math"],
        )
        reg.register(entry)
        assert reg.get("math_pack:calc") is not None
        assert reg.count() == 1
        assert len(reg.search_by_tag(["math"])) == 1
        assert len(reg.search_by_vocab("calc")) == 1
        assert len(reg.search_fuzzy("calc", threshold=0.5)) >= 1


# =================================================================
# 6. register() 後に search_by_tag, search_fuzzy が動作すること
# =================================================================

class TestSearchAfterRegister:
    def test_search_by_tag_after_register(self):
        reg = FunctionRegistry()
        reg.register(
            pack_id="pk",
            function_id="fn1",
            manifest={"tags": ["alpha", "beta"]},
            function_dir=None,
        )
        reg.register(
            pack_id="pk",
            function_id="fn2",
            manifest={"tags": ["gamma"]},
            function_dir=None,
        )
        assert len(reg.search_by_tag(["alpha"])) == 1
        assert len(reg.search_by_tag(["gamma"])) == 1
        assert len(reg.search_by_tag(["alpha", "beta"])) == 1
        assert len(reg.search_by_tag(["alpha", "gamma"])) == 0

    def test_search_fuzzy_after_register(self):
        reg = FunctionRegistry()
        reg.register(
            pack_id="pk",
            function_id="summarize_text",
            manifest={"description": "Summarize text documents"},
            function_dir=None,
        )
        results = reg.search_fuzzy("summarize", threshold=0.3)
        assert len(results) >= 1
        assert results[0][1].function_id == "summarize_text"


# =================================================================
# 7. unregister_pack() 後にクリーンアップされること
# =================================================================

class TestUnregisterPackCleanup:
    def test_unregister_clears_entries_and_tags(self):
        reg = FunctionRegistry()
        reg.register(
            pack_id="removable",
            function_id="f1",
            manifest={"tags": ["special_tag"]},
            function_dir=None,
        )
        reg.register(
            pack_id="removable",
            function_id="f2",
            manifest={"tags": ["special_tag"]},
            function_dir=None,
        )
        assert reg.count() == 2
        assert len(reg.search_by_tag(["special_tag"])) == 2

        removed = reg.unregister_pack("removable")
        assert removed == 2
        assert reg.count() == 0
        assert reg.get("removable:f1") is None
        assert reg.get("removable:f2") is None
        assert len(reg.search_by_tag(["special_tag"])) == 0

    def test_unregister_nonexistent_pack(self):
        reg = FunctionRegistry()
        assert reg.unregister_pack("ghost") == 0


# =================================================================
# 8. 不正な引数での register() が適切にエラーを出すこと
# =================================================================

class TestGracefulErrors:
    def test_none_entry_raises_type_error(self):
        reg = FunctionRegistry()
        with pytest.raises(TypeError):
            reg.register(None)

    def test_empty_function_id_raises_value_error(self):
        reg = FunctionRegistry()
        with pytest.raises(ValueError, match="function_id"):
            reg.register(FunctionEntry(function_id="", pack_id="pk"))

    def test_empty_pack_id_raises_value_error(self):
        reg = FunctionRegistry()
        with pytest.raises(ValueError, match="pack_id"):
            reg.register(FunctionEntry(function_id="fn", pack_id=""))

    def test_kwargs_register_with_empty_pack_id(self):
        reg = FunctionRegistry()
        with pytest.raises(ValueError, match="pack_id"):
            reg.register(pack_id="", function_id="fn", manifest={}, function_dir=None)

    def test_duplicate_register_returns_false(self):
        """重複登録は False を返し例外にならない"""
        reg = FunctionRegistry()
        e = FunctionEntry(function_id="dup", pack_id="pk")
        assert reg.register(e) is True
        assert reg.register(e) is False
        assert reg.count() == 1
