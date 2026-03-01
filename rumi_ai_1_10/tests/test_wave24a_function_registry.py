"""
test_wave24a_function_registry.py - FunctionRegistry テスト

Wave 24 Agent A: FunctionRegistry の単体テスト。
20 件以上のテストケースで登録・検索・解除・スレッドセーフ等を網羅する。
"""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core_runtime.function_registry import (
    BulkRegisterResult,
    FunctionEntry,
    FunctionRegistry,
)


# ===================================================================
# ヘルパー
# ===================================================================

def _make_entry(
    function_id: str = "summarize",
    pack_id: str = "text_utils",
    **kwargs,
) -> FunctionEntry:
    """テスト用 FunctionEntry を生成する"""
    defaults = dict(
        description="Summarize text",
        requires=["net"],
        caller_requires=[],
        host_execution=False,
        tags=["nlp", "text"],
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        function_dir=Path("/tmp/packs/text_utils/functions/summarize"),
        main_py_path=Path("/tmp/packs/text_utils/functions/summarize/main.py"),
    )
    defaults.update(kwargs)
    return FunctionEntry(function_id=function_id, pack_id=pack_id, **defaults)


def _make_vocab_mock() -> MagicMock:
    """VocabRegistry のモックを生成する"""
    mock = MagicMock()
    # デフォルト: resolve は入力をそのまま返す
    mock.resolve.side_effect = lambda term, to_preferred=True: term.strip().lower()
    # デフォルト: get_group は単一要素リスト
    mock.get_group.side_effect = lambda term: [term.strip().lower()]
    mock.is_synonym.return_value = False
    return mock


# ===================================================================
# 1. 登録と取得（完全一致）
# ===================================================================

class TestRegisterAndGet:
    def test_register_and_get_exact(self):
        reg = FunctionRegistry()
        entry = _make_entry()
        assert reg.register(entry) is True
        result = reg.get("text_utils:summarize")
        assert result is not None
        assert result.function_id == "summarize"
        assert result.pack_id == "text_utils"

    def test_get_nonexistent_returns_none(self):
        reg = FunctionRegistry()
        assert reg.get("no_pack:no_func") is None

    def test_qualified_name_format(self):
        entry = _make_entry(function_id="translate", pack_id="lang_pack")
        assert entry.qualified_name == "lang_pack:translate"


# ===================================================================
# 2. Pack 単位の登録・解除
# ===================================================================

class TestPackOperations:
    def test_register_pack_bulk(self):
        reg = FunctionRegistry()
        defs = [
            {
                "function_id": "func_a",
                "description": "Function A",
                "requires": [],
                "tags": ["tag1"],
                "function_dir": "/tmp/a",
                "main_py_path": "/tmp/a/main.py",
            },
            {
                "function_id": "func_b",
                "description": "Function B",
                "requires": ["net"],
                "tags": ["tag2"],
                "function_dir": "/tmp/b",
                "main_py_path": "/tmp/b/main.py",
            },
        ]
        result = reg.register_pack("my_pack", defs)
        assert result.success is True
        assert result.registered == 2
        assert result.skipped == 0
        assert reg.get("my_pack:func_a") is not None
        assert reg.get("my_pack:func_b") is not None

    def test_unregister_pack(self):
        reg = FunctionRegistry()
        entry1 = _make_entry(function_id="f1", pack_id="pk")
        entry2 = _make_entry(function_id="f2", pack_id="pk")
        reg.register(entry1)
        reg.register(entry2)
        assert reg.count() == 2

        removed = reg.unregister_pack("pk")
        assert removed == 2
        assert reg.get("pk:f1") is None
        assert reg.get("pk:f2") is None
        assert reg.count() == 0

    def test_unregister_nonexistent_pack(self):
        reg = FunctionRegistry()
        assert reg.unregister_pack("ghost") == 0

    def test_register_result_structure(self):
        reg = FunctionRegistry()
        defs = [{"function_id": "ok", "description": "OK"}]
        result = reg.register_pack("p", defs)
        assert isinstance(result, BulkRegisterResult)
        assert hasattr(result, "success")
        assert hasattr(result, "registered")
        assert hasattr(result, "skipped")
        assert hasattr(result, "errors")


# ===================================================================
# 3. 一覧取得
# ===================================================================

class TestListing:
    def test_list_all(self):
        reg = FunctionRegistry()
        reg.register(_make_entry(function_id="a", pack_id="p1"))
        reg.register(_make_entry(function_id="b", pack_id="p2"))
        all_entries = reg.list_all()
        assert len(all_entries) == 2

    def test_list_by_pack(self):
        reg = FunctionRegistry()
        reg.register(_make_entry(function_id="a", pack_id="p1"))
        reg.register(_make_entry(function_id="b", pack_id="p1"))
        reg.register(_make_entry(function_id="c", pack_id="p2"))
        assert len(reg.list_by_pack("p1")) == 2
        assert len(reg.list_by_pack("p2")) == 1
        assert len(reg.list_by_pack("p3")) == 0


# ===================================================================
# 4. vocab 同義語検索
# ===================================================================

class TestVocabSearch:
    def test_vocab_synonym_search(self):
        """resolve で正規化したキーワードでヒットする"""
        vocab = _make_vocab_mock()
        # "summarise" → resolve → "summarize"（正規化）
        vocab.resolve.side_effect = lambda t, to_preferred=True: (
            "summarize" if t.strip().lower() in ("summarise", "summarize") else t.strip().lower()
        )
        vocab.get_group.side_effect = lambda t: (
            ["summarize", "summarise"]
            if t.strip().lower() in ("summarise", "summarize")
            else [t.strip().lower()]
        )

        reg = FunctionRegistry(vocab_registry=vocab)
        reg.register(_make_entry(function_id="summarize", pack_id="pk"))

        # "summarise" で検索 → resolve("summarise") = "summarize" → ヒット
        results = reg.search_by_vocab("summarise")
        assert len(results) == 1
        assert results[0].function_id == "summarize"

    def test_vocab_synonym_search_group_expansion(self):
        """get_group で返った同義語全てで検索する"""
        vocab = _make_vocab_mock()
        vocab.resolve.side_effect = lambda t, to_preferred=True: (
            "summarize" if t.strip().lower() in ("recap", "summarize", "summarise") else t.strip().lower()
        )
        vocab.get_group.side_effect = lambda t: (
            ["summarize", "summarise", "recap"]
            if t.strip().lower() in ("recap", "summarize", "summarise")
            else [t.strip().lower()]
        )

        reg = FunctionRegistry(vocab_registry=vocab)
        reg.register(_make_entry(function_id="summarize", pack_id="pk"))

        results = reg.search_by_vocab("recap")
        assert len(results) == 1
        assert results[0].function_id == "summarize"

    def test_vocab_unavailable_fallback(self):
        """VocabRegistry が None でも完全一致は動作する"""
        reg = FunctionRegistry(vocab_registry=None)
        reg.register(_make_entry(function_id="translate", pack_id="pk"))

        # 完全一致取得は動く
        assert reg.get("pk:translate") is not None

        # vocab 検索は function_id そのものでマッチ
        results = reg.search_by_vocab("translate")
        assert len(results) == 1

    def test_vocab_search_no_match(self):
        """マッチしないキーワードでは空リスト"""
        reg = FunctionRegistry()
        reg.register(_make_entry(function_id="summarize", pack_id="pk"))
        results = reg.search_by_vocab("xyzzy_no_match")
        assert results == []


# ===================================================================
# 5. タグ検索
# ===================================================================

class TestTagSearch:
    def test_tag_search_single(self):
        reg = FunctionRegistry()
        reg.register(_make_entry(function_id="f1", pack_id="p", tags=["nlp", "text"]))
        reg.register(_make_entry(function_id="f2", pack_id="p", tags=["image"]))

        results = reg.search_by_tag(["nlp"])
        assert len(results) == 1
        assert results[0].function_id == "f1"

    def test_tag_search_multiple_and(self):
        reg = FunctionRegistry()
        reg.register(_make_entry(function_id="f1", pack_id="p", tags=["nlp", "text"]))
        reg.register(_make_entry(function_id="f2", pack_id="p", tags=["nlp", "audio"]))

        results = reg.search_by_tag(["nlp", "text"])
        assert len(results) == 1
        assert results[0].function_id == "f1"

    def test_tag_search_empty(self):
        reg = FunctionRegistry()
        assert reg.search_by_tag([]) == []

    def test_tag_vocab_normalization(self):
        """タグにも vocab.resolve() が適用される"""
        vocab = _make_vocab_mock()
        vocab.resolve.side_effect = lambda t, to_preferred=True: (
            "nlp" if t.strip().lower() in ("nlp", "natural_language") else t.strip().lower()
        )
        vocab.get_group.side_effect = lambda t: [t.strip().lower()]

        reg = FunctionRegistry(vocab_registry=vocab)
        # 登録時にタグ "natural_language" が "nlp" に正規化される
        reg.register(_make_entry(function_id="f1", pack_id="p", tags=["natural_language"]))

        # "nlp" で検索 → "nlp" に正規化 → ヒット
        results = reg.search_by_tag(["nlp"])
        assert len(results) == 1


# ===================================================================
# 6. ファジー検索
# ===================================================================

class TestFuzzySearch:
    def test_fuzzy_search_above_threshold(self):
        reg = FunctionRegistry()
        reg.register(_make_entry(function_id="summarize", pack_id="p",
                                  description="Summarize text", tags=[]))

        results = reg.search_fuzzy("summarize", threshold=0.3)
        assert len(results) >= 1
        assert results[0][1].function_id == "summarize"

    def test_fuzzy_search_below_threshold(self):
        reg = FunctionRegistry()
        reg.register(_make_entry(function_id="summarize_text", pack_id="p"))

        results = reg.search_fuzzy("zzzzz_completely_different", threshold=0.9)
        assert len(results) == 0

    def test_fuzzy_search_ordering(self):
        """類似度が高い方が先に来る"""
        reg = FunctionRegistry()
        reg.register(_make_entry(function_id="summarize", pack_id="p",
                                  description="Summarize text", tags=[]))
        reg.register(_make_entry(function_id="analyze", pack_id="p",
                                  description="Analyze data", tags=[]))

        results = reg.search_fuzzy("summarize", threshold=0.1)
        assert len(results) == 2
        # "summarize" により近い方が先
        assert results[0][0] >= results[1][0]
        assert results[0][1].function_id == "summarize"

    def test_fuzzy_search_empty_query(self):
        reg = FunctionRegistry()
        reg.register(_make_entry())
        assert reg.search_fuzzy("") == []


# ===================================================================
# 7. 重複登録
# ===================================================================

class TestDuplicateRegistration:
    def test_duplicate_registration_skipped(self):
        reg = FunctionRegistry()
        e1 = _make_entry(function_id="f", pack_id="p", description="first")
        e2 = _make_entry(function_id="f", pack_id="p", description="second")
        assert reg.register(e1) is True
        assert reg.register(e2) is False  # 先勝ち
        assert reg.get("p:f").description == "first"
        assert reg.count() == 1


# ===================================================================
# 8. host_execution フラグ
# ===================================================================

class TestHostExecution:
    def test_host_execution_flag_preserved(self):
        reg = FunctionRegistry()
        entry = _make_entry(host_execution=True)
        reg.register(entry)
        result = reg.get(entry.qualified_name)
        assert result is not None
        assert result.host_execution is True

    def test_host_execution_default_false(self):
        reg = FunctionRegistry()
        entry = _make_entry()  # default host_execution=False
        reg.register(entry)
        result = reg.get(entry.qualified_name)
        assert result.host_execution is False


# ===================================================================
# 9. スレッドセーフ
# ===================================================================

class TestThreadSafety:
    def test_concurrent_register_and_get(self):
        reg = FunctionRegistry()
        errors = []

        def register_worker(worker_id: int):
            try:
                for i in range(50):
                    entry = _make_entry(
                        function_id=f"func_{worker_id}_{i}",
                        pack_id=f"pack_{worker_id}",
                        tags=[f"tag_{worker_id}"],
                    )
                    reg.register(entry)
            except Exception as e:
                errors.append(e)

        def read_worker():
            try:
                for _ in range(100):
                    reg.list_all()
                    reg.search_by_tag(["tag_0"])
                    reg.search_fuzzy("func", threshold=0.1)
            except Exception as e:
                errors.append(e)

        threads = []
        for wid in range(4):
            threads.append(threading.Thread(target=register_worker, args=(wid,)))
        for _ in range(2):
            threads.append(threading.Thread(target=read_worker))

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert errors == [], f"Thread errors: {errors}"
        assert reg.count() == 4 * 50


# ===================================================================
# 10. 不正な引数
# ===================================================================

class TestInvalidArgs:
    def test_empty_function_id_raises(self):
        reg = FunctionRegistry()
        with pytest.raises(ValueError, match="function_id"):
            reg.register(_make_entry(function_id=""))

    def test_empty_pack_id_raises(self):
        reg = FunctionRegistry()
        with pytest.raises(ValueError, match="pack_id"):
            reg.register(_make_entry(pack_id=""))

    def test_whitespace_only_function_id_raises(self):
        reg = FunctionRegistry()
        with pytest.raises(ValueError, match="function_id"):
            reg.register(_make_entry(function_id="   "))

    def test_none_entry_raises_type_error(self):
        reg = FunctionRegistry()
        with pytest.raises(TypeError):
            reg.register(None)

    def test_register_pack_empty_pack_id(self):
        reg = FunctionRegistry()
        with pytest.raises(ValueError, match="pack_id"):
            reg.register_pack("", [])


# ===================================================================
# 11. to_dict / count / list_packs
# ===================================================================

class TestMisc:
    def test_to_dict(self):
        entry = _make_entry()
        d = entry.to_dict()
        assert d["qualified_name"] == "text_utils:summarize"
        assert d["function_id"] == "summarize"
        assert d["pack_id"] == "text_utils"
        assert isinstance(d["tags"], list)

    def test_list_packs(self):
        reg = FunctionRegistry()
        reg.register(_make_entry(function_id="a", pack_id="p1"))
        reg.register(_make_entry(function_id="b", pack_id="p2"))
        packs = reg.list_packs()
        assert set(packs) == {"p1", "p2"}

    def test_clear(self):
        reg = FunctionRegistry()
        reg.register(_make_entry())
        assert reg.count() == 1
        reg.clear()
        assert reg.count() == 0
        assert reg.list_all() == []

    def test_unregister_pack_clears_tag_index(self):
        """unregister_pack 後にタグ検索でヒットしない"""
        reg = FunctionRegistry()
        reg.register(_make_entry(function_id="f1", pack_id="pk", tags=["special"]))
        assert len(reg.search_by_tag(["special"])) == 1
        reg.unregister_pack("pk")
        assert len(reg.search_by_tag(["special"])) == 0
