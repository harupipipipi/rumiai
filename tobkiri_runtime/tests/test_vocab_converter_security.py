"""
test_vocab_converter_security.py - Converter セキュリティのテスト

対象: core_runtime/vocab_registry.py (C-3-L1, C-3-L2, C-3-L3)
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core_runtime.vocab_registry import (
    ConverterASTChecker,
    ConverterIntegrityChecker,
    ConverterPolicy,
    VocabRegistry,
)


# ===================================================================
# C-3-L1: ConverterPolicy + register_converter
# ===================================================================

class TestPolicyFileSize:
    def test_policy_file_size_check(self, tmp_path):
        big_file = tmp_path / "big.py"
        big_file.write_text(
            "def convert(data): return data\n" + "# pad\n" * 20_000,
            encoding="utf-8",
        )
        policy = ConverterPolicy(max_file_size_bytes=1_000)
        vr = VocabRegistry()
        result = vr.register_converter(
            "a", "b", big_file, policy=policy,
        )
        assert result is False


class TestPolicyBlockedImportSubprocess:
    def test_policy_blocked_import_subprocess(self, tmp_path):
        bad_file = tmp_path / "bad_sp.py"
        bad_file.write_text(
            "import subprocess\ndef convert(data): return data\n",
            encoding="utf-8",
        )
        policy = ConverterPolicy()
        vr = VocabRegistry()
        result = vr.register_converter(
            "a", "b", bad_file, policy=policy,
        )
        assert result is False


class TestPolicyBlockedImportOsSystem:
    def test_policy_blocked_import_os_system(self, tmp_path):
        bad_file = tmp_path / "bad_os.py"
        bad_file.write_text(
            "from os import system\ndef convert(data): return data\n",
            encoding="utf-8",
        )
        policy = ConverterPolicy()
        vr = VocabRegistry()
        result = vr.register_converter(
            "a", "b", bad_file, policy=policy,
        )
        assert result is False


# ===================================================================
# C-3-L3: ConverterASTChecker
# ===================================================================

class TestASTCheckerExec:
    def test_ast_checker_exec_call(self):
        checker = ConverterASTChecker()
        source = "def convert(data):\n    exec('pass')\n    return data\n"
        is_safe, warns = checker.check(source, set())
        assert is_safe is False
        assert any("exec" in w for w in warns)


class TestASTCheckerEval:
    def test_ast_checker_eval_call(self):
        checker = ConverterASTChecker()
        source = "def convert(data):\n    return eval('data')\n"
        is_safe, warns = checker.check(source, set())
        assert is_safe is False
        assert any("eval" in w for w in warns)


class TestASTCheckerClean:
    def test_ast_checker_clean_file(self):
        checker = ConverterASTChecker()
        source = (
            "import json\n"
            "\n"
            "def convert(data):\n"
            "    return json.dumps(data)\n"
        )
        is_safe, warns = checker.check(source, {"subprocess", "socket"})
        assert is_safe is True
        assert warns == []


# ===================================================================
# C-3-L2: ConverterIntegrityChecker
# ===================================================================

class TestIntegrityMissingConvert:
    def test_integrity_checker_missing_convert(self, tmp_path):
        no_convert = tmp_path / "no_convert.py"
        no_convert.write_text(
            "def transform(data): return data\n",
            encoding="utf-8",
        )
        checker = ConverterIntegrityChecker()
        is_safe, warns = checker.check_file(no_convert)
        assert is_safe is False
        assert any("convert()" in w for w in warns)


class TestIntegritySyntaxError:
    def test_integrity_checker_syntax_error(self, tmp_path):
        bad_syntax = tmp_path / "bad_syntax.py"
        bad_syntax.write_text(
            "def convert(data\n    return data\n",
            encoding="utf-8",
        )
        checker = ConverterIntegrityChecker()
        is_safe, warns = checker.check_file(bad_syntax)
        assert is_safe is False
        assert any("SyntaxError" in w for w in warns)
