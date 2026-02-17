"""
test_converter_ast_level1.py - Converter AST検査 Level 1 テスト

ConverterASTChecker.check_with_locals() の7シナリオをカバーする。

シナリオ一覧:
    1. converter 単体に import subprocess → 拒否
    2. converter → helper.py → import os → 拒否
    3. converter → helper.py（クリーン） → 許可
    4. converter → import requests（ローカル .py なし） → 許可
    5. converter → helper → utils → import socket → 拒否
    6. 循環: converter → helper → converter → 無限ループせず正常終了
    7. converter外へのimport（from ..other） → スキップ
"""
import textwrap
from pathlib import Path

import pytest

from core_runtime.vocab_registry import ConverterASTChecker


# テスト用の blocked imports セット
BLOCKED = {"subprocess", "os", "socket"}


class TestConverterASTLevel1:
    """check_with_locals() の Level 1 再帰検査テスト"""

    @staticmethod
    def _make_file(dir_path: Path, name: str, code: str) -> Path:
        """ヘルパー: 指定ディレクトリにPythonファイルを作成する"""
        p = dir_path / name
        p.write_text(textwrap.dedent(code), encoding="utf-8")
        return p

    # ------------------------------------------------------------------
    # シナリオ 1: converter 単体に import subprocess → 拒否
    # ------------------------------------------------------------------
    def test_scenario1_single_blocked_import(self, tmp_path: Path) -> None:
        conv = self._make_file(tmp_path, "converter.py", """\
            import subprocess
            def convert(data):
                return data
        """)
        checker = ConverterASTChecker()
        is_safe, violations = checker.check_with_locals(conv, BLOCKED)
        assert not is_safe
        assert any("subprocess" in v for v in violations)

    # ------------------------------------------------------------------
    # シナリオ 2: converter → helper.py → import os → 拒否
    # ------------------------------------------------------------------
    def test_scenario2_helper_blocked_import(self, tmp_path: Path) -> None:
        conv = self._make_file(tmp_path, "converter.py", """\
            from .helper import func
            def convert(data):
                return func(data)
        """)
        self._make_file(tmp_path, "helper.py", """\
            import os
            def func(data):
                return data
        """)
        checker = ConverterASTChecker()
        is_safe, violations = checker.check_with_locals(conv, BLOCKED)
        assert not is_safe
        assert any("os" in v for v in violations)
        # helper.py が違反元として報告されることを確認
        assert any("helper.py" in v for v in violations)

    # ------------------------------------------------------------------
    # シナリオ 3: converter → helper.py（クリーン） → 許可
    # ------------------------------------------------------------------
    def test_scenario3_helper_clean(self, tmp_path: Path) -> None:
        conv = self._make_file(tmp_path, "converter.py", """\
            from .helper import func
            def convert(data):
                return func(data)
        """)
        self._make_file(tmp_path, "helper.py", """\
            def func(data):
                return data
        """)
        checker = ConverterASTChecker()
        is_safe, violations = checker.check_with_locals(conv, BLOCKED)
        assert is_safe
        assert violations == []

    # ------------------------------------------------------------------
    # シナリオ 4: converter → import requests（ローカル .py なし） → 許可
    # ------------------------------------------------------------------
    def test_scenario4_external_allowed_import(self, tmp_path: Path) -> None:
        conv = self._make_file(tmp_path, "converter.py", """\
            import requests
            def convert(data):
                return data
        """)
        checker = ConverterASTChecker()
        is_safe, violations = checker.check_with_locals(conv, BLOCKED)
        assert is_safe
        assert violations == []

    # ------------------------------------------------------------------
    # シナリオ 5: converter → helper → utils → import socket → 拒否
    # ------------------------------------------------------------------
    def test_scenario5_transitive_blocked_import(self, tmp_path: Path) -> None:
        conv = self._make_file(tmp_path, "converter.py", """\
            from .helper import func
            def convert(data):
                return func(data)
        """)
        self._make_file(tmp_path, "helper.py", """\
            from .utils import do_thing
            def func(data):
                return do_thing(data)
        """)
        self._make_file(tmp_path, "utils.py", """\
            import socket
            def do_thing(data):
                return data
        """)
        checker = ConverterASTChecker()
        is_safe, violations = checker.check_with_locals(conv, BLOCKED)
        assert not is_safe
        assert any("socket" in v for v in violations)
        # utils.py が違反元として報告されることを確認
        assert any("utils.py" in v for v in violations)

    # ------------------------------------------------------------------
    # シナリオ 6: 循環 converter → helper → converter → 無限ループせず正常終了
    # ------------------------------------------------------------------
    def test_scenario6_circular_import(self, tmp_path: Path) -> None:
        conv = self._make_file(tmp_path, "converter.py", """\
            from .helper import func
            def convert(data):
                return func(data)
        """)
        self._make_file(tmp_path, "helper.py", """\
            from .converter import convert
            def func(data):
                return data
        """)
        checker = ConverterASTChecker()
        # 無限ループせずに正常終了すること
        is_safe, violations = checker.check_with_locals(conv, BLOCKED)
        assert is_safe
        assert violations == []

    # ------------------------------------------------------------------
    # シナリオ 7: converter外へのimport（from ..other） → スキップ
    # ------------------------------------------------------------------
    def test_scenario7_parent_relative_import_skipped(self, tmp_path: Path) -> None:
        conv = self._make_file(tmp_path, "converter.py", """\
            from ..other import something
            def convert(data):
                return data
        """)
        checker = ConverterASTChecker()
        is_safe, violations = checker.check_with_locals(conv, BLOCKED)
        assert is_safe
        assert violations == []
