"""
test_vocab_registry.py - P0: VocabRegistry のテスト

対象: core_runtime/vocab_registry.py
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core_runtime.vocab_registry import VocabRegistry


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
