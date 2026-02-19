"""
test_vocab_registry.py - P0: VocabRegistry のテスト

対象: core_runtime/vocab_registry.py
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core_runtime.vocab_registry import (
    CollisionStrategy,
    MAX_NORMALIZE_DEPTH,
    VocabKeyCollisionError,
    VocabRegistry,
)


# ===================================================================
# register_group / resolve
# ===================================================================

class TestRegisterAndResolve:

    def test_register_group_basic(self):
        vr = VocabRegistry()
        gid = vr.register_group(["tool", "function_calling", "tools"])
        assert gid != ""
        assert vr.resolve("function_calling") == "tool"
        assert vr.resolve("tools") == "tool"
        assert vr.resolve("tool") == "tool"

    def test_resolve_unknown_returns_self(self):
        vr = VocabRegistry()
        assert vr.resolve("unknown_term") == "unknown_term"

    def test_register_empty_list(self):
        vr = VocabRegistry()
        gid = vr.register_group([])
        assert gid == ""

    def test_register_whitespace_only(self):
        vr = VocabRegistry()
        gid = vr.register_group(["  ", "  "])
        assert gid == ""

    def test_case_insensitive(self):
        vr = VocabRegistry()
        vr.register_group(["Tool", "FUNCTION_CALLING"])
        assert vr.resolve("tool") == "tool"
        assert vr.resolve("TOOL") == "tool"
        assert vr.resolve("function_calling") == "tool"

    def test_preferred_is_first_term(self):
        vr = VocabRegistry()
        vr.register_group(["alpha", "beta", "gamma"])
        assert vr.get_preferred("beta") == "alpha"
        assert vr.get_preferred("gamma") == "alpha"

    def test_merge_overlapping_groups(self):
        vr = VocabRegistry()
        vr.register_group(["a", "b"])
        vr.register_group(["b", "c"])
        # b is shared, so a, b, c should be in the same group
        assert vr.is_synonym("a", "c") is True

    def test_register_synonym(self):
        vr = VocabRegistry()
        vr.register_synonym("x", "y")
        assert vr.is_synonym("x", "y") is True


# ===================================================================
# is_synonym
# ===================================================================

class TestIsSynonym:

    def test_same_group(self):
        vr = VocabRegistry()
        vr.register_group(["a", "b", "c"])
        assert vr.is_synonym("a", "b") is True
        assert vr.is_synonym("b", "c") is True
        assert vr.is_synonym("a", "c") is True

    def test_different_groups(self):
        vr = VocabRegistry()
        vr.register_group(["a", "b"])
        vr.register_group(["x", "y"])
        assert vr.is_synonym("a", "x") is False

    def test_unknown_terms(self):
        vr = VocabRegistry()
        assert vr.is_synonym("unknown1", "unknown2") is False

    def test_same_term(self):
        vr = VocabRegistry()
        assert vr.is_synonym("anything", "anything") is True


# ===================================================================
# get_group
# ===================================================================

class TestGetGroup:

    def test_returns_all_members(self):
        vr = VocabRegistry()
        vr.register_group(["tool", "function_calling", "tools"])
        group = vr.get_group("function_calling")
        assert "tool" in group
        assert "function_calling" in group
        assert "tools" in group

    def test_preferred_first(self):
        vr = VocabRegistry()
        vr.register_group(["preferred", "alt1", "alt2"])
        group = vr.get_group("alt1")
        assert group[0] == "preferred"

    def test_unknown_returns_singleton(self):
        vr = VocabRegistry()
        group = vr.get_group("unknown")
        assert group == ["unknown"]


# ===================================================================
# resolve_to
# ===================================================================

class TestResolveTo:

    def test_resolve_to_target(self):
        vr = VocabRegistry()
        vr.register_group(["tool", "function_calling"])
        assert vr.resolve_to("tool", "function_calling") == "function_calling"

    def test_resolve_to_nonmember(self):
        vr = VocabRegistry()
        vr.register_group(["tool", "function_calling"])
        assert vr.resolve_to("tool", "unknown") == "tool"


# ===================================================================
# load_vocab_file
# ===================================================================

class TestLoadVocabFile:

    def test_load_basic_file(self, tmp_path):
        vocab_file = tmp_path / "vocab.txt"
        vocab_file.write_text(
            "tool, function_calling, tools\n"
            "thinking_budget, reasoning_effort\n",
            encoding="utf-8",
        )
        vr = VocabRegistry()
        count = vr.load_vocab_file(vocab_file)
        assert count == 2
        assert vr.resolve("function_calling") == "tool"
        assert vr.resolve("reasoning_effort") == "thinking_budget"

    def test_load_with_comments_and_empty_lines(self, tmp_path):
        vocab_file = tmp_path / "vocab.txt"
        vocab_file.write_text(
            "# This is a comment\n"
            "\n"
            "   \n"
            "alpha, beta\n"
            "# Another comment\n"
            "gamma, delta\n",
            encoding="utf-8",
        )
        vr = VocabRegistry()
        count = vr.load_vocab_file(vocab_file)
        assert count == 2

    def test_load_equals_separator(self, tmp_path):
        vocab_file = tmp_path / "vocab.txt"
        vocab_file.write_text("left = right\n", encoding="utf-8")
        vr = VocabRegistry()
        count = vr.load_vocab_file(vocab_file)
        assert count == 1
        assert vr.is_synonym("left", "right") is True

    def test_load_single_term_line_skipped(self, tmp_path):
        vocab_file = tmp_path / "vocab.txt"
        vocab_file.write_text("lonely\n", encoding="utf-8")
        vr = VocabRegistry()
        count = vr.load_vocab_file(vocab_file)
        assert count == 0

    def test_load_nonexistent_file(self, tmp_path):
        vr = VocabRegistry()
        count = vr.load_vocab_file(tmp_path / "nonexistent.txt")
        assert count == 0


# ===================================================================
# converter registration and execution
# ===================================================================

class TestConverter:

    def test_register_and_convert(self, tmp_path):
        converter_file = tmp_path / "tool_to_fc.py"
        converter_file.write_text(
            "def convert(data):\n"
            "    return {'converted': True, 'original': data}\n",
            encoding="utf-8",
        )
        vr = VocabRegistry()
        assert vr.register_converter("tool", "fc", converter_file) is True
        assert vr.has_converter("tool", "fc") is True
        result, success = vr.convert("tool", "fc", {"tools": []})
        assert success is True
        assert result["converted"] is True

    def test_convert_no_converter(self):
        vr = VocabRegistry()
        result, success = vr.convert("tool", "nonexistent", {"data": 1})
        assert success is False
        assert result == {"data": 1}  # original data returned

    def test_register_nonexistent_file(self, tmp_path):
        vr = VocabRegistry()
        assert vr.register_converter(
            "a", "b", tmp_path / "nonexistent.py"
        ) is False

    def test_converter_exception_handled(self, tmp_path):
        converter_file = tmp_path / "bad_converter.py"
        converter_file.write_text(
            "def convert(data):\n"
            "    raise ValueError('boom')\n",
            encoding="utf-8",
        )
        vr = VocabRegistry()
        vr.register_converter("a", "b", converter_file)
        result, success = vr.convert("a", "b", "input")
        assert success is False
        assert result == "input"  # original data returned

    def test_converter_with_context(self, tmp_path):
        converter_file = tmp_path / "ctx_converter.py"
        converter_file.write_text(
            "def convert(data, context):\n"
            "    return {'data': data, 'ctx': context}\n",
            encoding="utf-8",
        )
        vr = VocabRegistry()
        vr.register_converter("a", "b", converter_file)
        result, success = vr.convert("a", "b", "input", context={"key": "val"})
        assert success is True
        assert result["ctx"]["key"] == "val"


# ===================================================================
# clear / list_groups / list_converters
# ===================================================================

class TestClearAndList:

    def test_clear(self):
        vr = VocabRegistry()
        vr.register_group(["a", "b"])
        vr.clear()
        assert vr.resolve("a") == "a"
        assert vr.list_groups() == []

    def test_list_groups(self):
        vr = VocabRegistry()
        vr.register_group(["tool", "fc"])
        groups = vr.list_groups()
        assert len(groups) == 1
        assert groups[0]["preferred"] == "tool"

    def test_list_converters(self, tmp_path):
        converter_file = tmp_path / "a_to_b.py"
        converter_file.write_text("def convert(d): return d\n", encoding="utf-8")
        vr = VocabRegistry()
        vr.register_converter("a", "b", converter_file)
        converters = vr.list_converters()
        assert len(converters) == 1
        assert converters[0]["from"] == "a"
        assert converters[0]["to"] == "b"


# ===================================================================
# load_pack_vocab
# ===================================================================

class TestLoadPackVocab:

    def test_load_pack_vocab(self, tmp_path):
        pack_dir = tmp_path / "mypack"
        pack_dir.mkdir()
        (pack_dir / "vocab.txt").write_text(
            "tool, function_calling\n", encoding="utf-8"
        )
        converters_dir = pack_dir / "converters"
        converters_dir.mkdir()
        (converters_dir / "tool_to_fc.py").write_text(
            "def convert(d): return d\n", encoding="utf-8"
        )

        vr = VocabRegistry()
        result = vr.load_pack_vocab(pack_dir, "mypack")
        assert result["groups"] == 1
        assert result["converters"] == 1

    def test_skip_already_loaded_pack(self, tmp_path):
        pack_dir = tmp_path / "mypack"
        pack_dir.mkdir()
        (pack_dir / "vocab.txt").write_text(
            "a, b\n", encoding="utf-8"
        )
        vr = VocabRegistry()
        r1 = vr.load_pack_vocab(pack_dir, "mypack")
        r2 = vr.load_pack_vocab(pack_dir, "mypack")
        assert r1["groups"] == 1
        assert r2["groups"] == 0  # already loaded, skipped


# ===================================================================
# normalize_dict_keys (I-11)
# ===================================================================

class TestNormalizeDictKeys:

    def test_basic_normalization(self):
        vr = VocabRegistry()
        vr.register_group(["tool", "function_calling", "tools"])
        data = {"function_calling": [{"name": "search"}]}
        result, changes = vr.normalize_dict_keys(data)
        assert "tool" in result
        assert result["tool"] == [{"name": "search"}]
        assert len(changes) > 0

    def test_no_change_when_preferred(self):
        vr = VocabRegistry()
        vr.register_group(["tool", "function_calling"])
        data = {"tool": [{"name": "search"}]}
        result, changes = vr.normalize_dict_keys(data)
        assert "tool" in result
        assert len(changes) == 0

    def test_unknown_key_unchanged(self):
        vr = VocabRegistry()
        data = {"unknown_key": "value"}
        result, changes = vr.normalize_dict_keys(data)
        assert "unknown_key" in result

    def test_nested_dict_normalized(self):
        vr = VocabRegistry()
        vr.register_group(["tool", "function_calling"])
        data = {"outer": {"function_calling": "inner_value"}}
        result, changes = vr.normalize_dict_keys(data)
        # normalize_dict_keys は再帰的にネストされた dict も正規化する
        assert "outer" in result
        # nested dict の function_calling は tool に変換される
        assert "tool" in result["outer"]

    def test_collision_detection(self):
        vr = VocabRegistry()
        vr.register_group(["tool", "function_calling"])
        data = {"tool": "v1", "function_calling": "v2"}
        result, changes = vr.normalize_dict_keys(data)
        # Both map to "tool" — collision should be detected in changes
        collision_entries = [c for c in changes if c[0].startswith("COLLISION:")]
        assert len(collision_entries) > 0

    def test_empty_dict(self):
        vr = VocabRegistry()
        result, changes = vr.normalize_dict_keys({})
        assert result == {}
        assert changes == []


# ===================================================================
# CollisionStrategy variants (C-2-impl)
# ===================================================================

class TestCollisionStrategyKeepFirst:

    def test_keep_first(self):
        vr = VocabRegistry()
        vr.register_group(["tool", "function_calling"])
        data = {"tool": "first", "function_calling": "second"}
        result, changes = vr.normalize_dict_keys(
            data, collision_strategy=CollisionStrategy.KEEP_FIRST
        )
        assert result["tool"] == "first"


class TestCollisionStrategyKeepLast:

    def test_keep_last(self):
        vr = VocabRegistry()
        vr.register_group(["tool", "function_calling"])
        data = {"tool": "first", "function_calling": "second"}
        result, changes = vr.normalize_dict_keys(
            data, collision_strategy=CollisionStrategy.KEEP_LAST
        )
        assert result["tool"] == "second"


class TestCollisionStrategyRaise:

    def test_raise_on_collision(self):
        vr = VocabRegistry()
        vr.register_group(["tool", "function_calling"])
        data = {"tool": "first", "function_calling": "second"}
        with pytest.raises(VocabKeyCollisionError) as exc_info:
            vr.normalize_dict_keys(
                data, collision_strategy=CollisionStrategy.RAISE
            )
        assert exc_info.value.key == "tool"
        assert exc_info.value.existing_value == "first"
        assert exc_info.value.new_value == "second"


class TestCollisionStrategyMergeList:

    def test_merge_list(self):
        vr = VocabRegistry()
        vr.register_group(["tool", "function_calling"])
        data = {"tool": "first", "function_calling": "second"}
        result, changes = vr.normalize_dict_keys(
            data, collision_strategy=CollisionStrategy.MERGE_LIST
        )
        assert result["tool"] == ["first", "second"]

    def test_merge_list_triple(self):
        vr = VocabRegistry()
        vr.register_group(["tool", "function_calling", "tools"])
        data = {"tool": "a", "function_calling": "b", "tools": "c"}
        result, changes = vr.normalize_dict_keys(
            data, collision_strategy=CollisionStrategy.MERGE_LIST
        )
        assert result["tool"] == ["a", "b", "c"]


class TestCollisionStrategyWarn:

    def test_warn_keeps_first(self):
        vr = VocabRegistry()
        vr.register_group(["tool", "function_calling"])
        data = {"tool": "first", "function_calling": "second"}
        result, changes = vr.normalize_dict_keys(
            data, collision_strategy=CollisionStrategy.WARN
        )
        # WARN = 警告ログ + keep_first
        assert result["tool"] == "first"


class TestCollisionOnCallback:

    def test_on_collision_callback(self):
        vr = VocabRegistry()
        vr.register_group(["tool", "function_calling"])
        data = {"tool": "first", "function_calling": "second"}

        def custom_handler(key, existing, new):
            return f"{existing}+{new}"

        result, changes = vr.normalize_dict_keys(
            data, on_collision=custom_handler
        )
        assert result["tool"] == "first+second"


# ===================================================================
# normalize_dict_keys: _ prefix skip
# ===================================================================

class TestNormalizeDictKeysUnderscorePrefix:

    def test_underscore_prefix_skipped(self):
        vr = VocabRegistry()
        vr.register_group(["tool", "function_calling"])
        data = {"_internal": "keep", "function_calling": "convert"}
        result, changes = vr.normalize_dict_keys(data)
        assert "_internal" in result
        assert "tool" in result
        # _internal は正規化対象外
        rename_changes = [
            (orig, norm) for orig, norm in changes
            if not orig.startswith("COLLISION:")
        ]
        originals = [c[0] for c in rename_changes]
        assert "_internal" not in originals

    def test_underscore_prefix_value_still_normalized(self):
        """_ プレフィックスキーの値（dict）は再帰的に正規化される。"""
        vr = VocabRegistry()
        vr.register_group(["tool", "function_calling"])
        data = {"_meta": {"function_calling": "inner"}}
        result, changes = vr.normalize_dict_keys(data)
        assert "_meta" in result
        assert "tool" in result["_meta"]


# ===================================================================
# normalize_dict_keys: MAX_NORMALIZE_DEPTH
# ===================================================================

class TestNormalizeDictKeysDepth:

    def test_max_depth_stops_recursion(self):
        vr = VocabRegistry()
        vr.register_group(["tool", "function_calling"])
        # MAX_NORMALIZE_DEPTH + 1 レベルのネストを構築
        data: dict = {"function_calling": "leaf"}
        for _ in range(MAX_NORMALIZE_DEPTH + 1):
            data = {"wrapper": data}
        result, changes = vr.normalize_dict_keys(data)
        # 最深部まで降りる
        inner = result
        for _ in range(MAX_NORMALIZE_DEPTH + 1):
            inner = inner["wrapper"]
        # 深さ制限超過: function_calling が変換されずに残っている
        assert "function_calling" in inner

    def test_within_depth_converted(self):
        vr = VocabRegistry()
        vr.register_group(["tool", "function_calling"])
        data = {"outer": {"function_calling": "val"}}
        result, changes = vr.normalize_dict_keys(data)
        assert "tool" in result["outer"]

    def test_list_within_depth_converted(self):
        """リスト内の dict も深さ制限内なら正規化される。"""
        vr = VocabRegistry()
        vr.register_group(["tool", "function_calling"])
        data = {"items": [{"function_calling": "v1"}, {"function_calling": "v2"}]}
        result, changes = vr.normalize_dict_keys(data)
        for item in result["items"]:
            assert "tool" in item


# ===================================================================
# get_registration_summary
# ===================================================================

class TestGetRegistrationSummary:

    def test_summary_basic(self, tmp_path):
        vr = VocabRegistry()
        vr.register_group(["tool", "function_calling"], source_pack="pack_a")
        vr.register_group(["alpha", "beta"], source_pack="pack_b")

        converter_file = tmp_path / "tool_to_fc.py"
        converter_file.write_text("def convert(d): return d\n", encoding="utf-8")
        vr.register_converter("tool", "fc", converter_file, source_pack="pack_a")

        summary = vr.get_registration_summary()
        assert summary["totals"]["groups"] == 2
        assert summary["totals"]["converters"] == 1
        assert "pack_a" in summary["groups_by_pack"]
        assert "pack_b" in summary["groups_by_pack"]
        assert "pack_a" in summary["converters_by_pack"]

    def test_summary_empty(self):
        vr = VocabRegistry()
        summary = vr.get_registration_summary()
        assert summary["totals"]["groups"] == 0
        assert summary["totals"]["converters"] == 0
        assert summary["totals"]["packs"] == 0
        assert summary["loaded_packs"] == []

    def test_summary_after_load_pack(self, tmp_path):
        pack_dir = tmp_path / "mypack"
        pack_dir.mkdir()
        (pack_dir / "vocab.txt").write_text(
            "tool, function_calling\n", encoding="utf-8"
        )
        vr = VocabRegistry()
        vr.load_pack_vocab(pack_dir, "mypack")

        summary = vr.get_registration_summary()
        assert "mypack" in summary["loaded_packs"]
        assert summary["totals"]["packs"] == 1

    def test_summary_unknown_pack(self):
        """source_pack 未指定のグループは _unknown に分類される。"""
        vr = VocabRegistry()
        vr.register_group(["x", "y"])  # source_pack=None
        summary = vr.get_registration_summary()
        assert "_unknown" in summary["groups_by_pack"]
