"""
test_wave28_30_multi_runtime.py

Wave 28-A / 28-B / 29 / 30 テスト
- FunctionEntry マルチランタイム対応
- capability_executor ランタイム分岐
- core function テーブル化
- extensions 検索メカニズム
"""

from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# テスト対象をインポート
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core_runtime.function_registry import FunctionEntry, FunctionRegistry


# =====================================================================
# Helpers
# =====================================================================

def _make_entry(**kwargs) -> FunctionEntry:
    """テスト用 FunctionEntry を簡易生成する。"""
    defaults = {
        "function_id": "test_func",
        "pack_id": "test_pack",
    }
    defaults.update(kwargs)
    return FunctionEntry(**defaults)


# =====================================================================
# Wave 28-A: FunctionEntry フィールド追加テスト
# =====================================================================

class TestWave28A_FunctionEntryFields:
    """FunctionEntry の新フィールドと _entry_from_kwargs のテスト。"""

    def test_runtime_python_default_main_py(self, tmp_path):
        """1. runtime='python' の FunctionEntry 作成 — main_py_path が設定される"""
        func_dir = tmp_path / "myfunc"
        func_dir.mkdir()
        (func_dir / "main.py").write_text("def run(ctx, args): pass")

        entry = FunctionRegistry._entry_from_kwargs(
            pack_id="pk",
            function_id="fn",
            manifest={"runtime": "python"},
            function_dir=func_dir,
        )
        assert entry.runtime == "python"
        assert entry.main_py_path is not None
        assert Path(entry.main_py_path).name == "main.py"
        assert entry.main_binary_path is None

    def test_runtime_binary_normal_path(self, tmp_path):
        """2. runtime='binary' + 正常パス — main_binary_path が設定される"""
        func_dir = tmp_path / "binfunc"
        func_dir.mkdir()
        bin_file = func_dir / "mybin"
        bin_file.write_text("#!/bin/sh\necho '{}'")
        bin_file.chmod(bin_file.stat().st_mode | stat.S_IEXEC)

        entry = FunctionRegistry._entry_from_kwargs(
            pack_id="pk",
            function_id="fn",
            manifest={"runtime": "binary", "main": "mybin"},
            function_dir=func_dir,
        )
        assert entry.runtime == "binary"
        assert entry.main_binary_path is not None
        assert Path(entry.main_binary_path).name == "mybin"
        assert entry.main_py_path is None

    def test_runtime_binary_path_traversal(self, tmp_path):
        """3. runtime='binary' + パストラバーサル (../../bin/x) — main_binary_path が None"""
        func_dir = tmp_path / "binfunc2"
        func_dir.mkdir()

        entry = FunctionRegistry._entry_from_kwargs(
            pack_id="pk",
            function_id="fn",
            manifest={"runtime": "binary", "main": "../../bin/x"},
            function_dir=func_dir,
        )
        assert entry.runtime == "binary"
        assert entry.main_binary_path is None

    def test_runtime_command_sets_command_list(self):
        """4. runtime='command' — command リストが設定される"""
        entry = FunctionRegistry._entry_from_kwargs(
            pack_id="pk",
            function_id="fn",
            manifest={"runtime": "command", "command": ["node", "index.js"]},
            function_dir=None,
        )
        assert entry.runtime == "command"
        assert entry.command == ["node", "index.js"]
        assert entry.main_py_path is None
        assert entry.main_binary_path is None

    def test_extensions_loaded_from_manifest(self, tmp_path):
        """5. extensions フィールドが manifest から読み込まれる"""
        func_dir = tmp_path / "extfunc"
        func_dir.mkdir()
        (func_dir / "main.py").write_text("def run(ctx, args): pass")

        ext_data = {"visual_editor": {"category": "NLP", "version": "1.0"}}
        entry = FunctionRegistry._entry_from_kwargs(
            pack_id="pk",
            function_id="fn",
            manifest={"extensions": ext_data},
            function_dir=func_dir,
        )
        assert entry.extensions == ext_data

    def test_to_dict_includes_new_fields(self):
        """to_dict に runtime, docker_image, has_extensions が含まれる"""
        entry = _make_entry(
            runtime="binary",
            docker_image="node:18-slim",
            extensions={"visual_editor": {}},
        )
        d = entry.to_dict()
        assert d["runtime"] == "binary"
        assert d["docker_image"] == "node:18-slim"
        assert d["has_extensions"] is True

    def test_to_dict_has_extensions_false_when_empty(self):
        """extensions が空の場合 has_extensions は False"""
        entry = _make_entry()
        d = entry.to_dict()
        assert d["has_extensions"] is False


# =====================================================================
# Wave 28-B: capability_executor ランタイム分岐テスト
# =====================================================================

class TestWave28B_RuntimeDispatch:
    """capability_executor のランタイム分岐テスト。"""

    def _make_executor(self):
        """最低限初期化された CapabilityExecutor のモックを返す。"""
        from core_runtime.capability_executor import CapabilityExecutor
        executor = CapabilityExecutor()
        executor._initialized = True
        executor._core_function_handlers = {
            "core_docker_capability": "docker_capability_handler",
        }
        return executor

    def test_host_execution_binary_rejected(self):
        """6. host_execution=True + runtime='binary' → security_violation エラー"""
        executor = self._make_executor()
        entry = _make_entry(
            host_execution=True,
            runtime="binary",
            manifest={},
        )
        resp = executor._execute_user_function(
            principal_id="user1",
            entry=entry,
            args={},
            request_id="req1",
            start_time=time.time(),
        )
        assert resp.success is False
        assert resp.error_type == "security_violation"
        assert "runtime='binary'" in resp.error

    def test_binary_execution_normal(self, tmp_path):
        """7. runtime='binary' 正常実行 — stdin/stdout プロトコル"""
        executor = self._make_executor()

        func_dir = tmp_path / "binfunc"
        func_dir.mkdir()
        # Python スクリプトをバイナリとして使う
        bin_file = func_dir / "mybin"
        bin_file.write_text(
            f"#!{sys.executable}\n"
            "import sys, json\n"
            "data = json.loads(sys.stdin.read())\n"
            "print(json.dumps({'result': 'ok', 'got_args': data.get('args', {})}))\n"
        )
        bin_file.chmod(bin_file.stat().st_mode | stat.S_IEXEC)

        entry = _make_entry(
            runtime="binary",
            main_binary_path=bin_file,
            function_dir=func_dir,
            manifest={},
        )
        resp = executor._execute_binary_function(
            principal_id="user1",
            entry=entry,
            args={"key": "value"},
            request_id="req1",
            start_time=time.time(),
        )
        assert resp.success is True
        assert resp.output["result"] == "ok"
        assert resp.output["got_args"] == {"key": "value"}

    def test_command_execution_normal(self, tmp_path):
        """8. runtime='command' 正常実行"""
        executor = self._make_executor()

        func_dir = tmp_path / "cmdfunc"
        func_dir.mkdir()
        script = func_dir / "run.py"
        script.write_text(
            "import sys, json\n"
            "data = json.loads(sys.stdin.read())\n"
            "print(json.dumps({'cmd_result': 'ok'}))\n"
        )

        entry = _make_entry(
            runtime="command",
            command=[sys.executable, str(script)],
            function_dir=func_dir,
            manifest={},
        )
        resp = executor._execute_command_function(
            principal_id="user1",
            entry=entry,
            args={},
            request_id="req1",
            start_time=time.time(),
        )
        assert resp.success is True
        assert resp.output["cmd_result"] == "ok"

    def test_docker_image_variable(self):
        """9. Docker イメージ可変化 — docker_image がビルダーに渡される"""
        executor = self._make_executor()

        mock_builder_cls = MagicMock()
        mock_builder_instance = MagicMock()
        mock_builder_cls.return_value = mock_builder_instance
        mock_builder_instance.build.return_value = ["docker", "run", "test"]

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = '{"ok": true}'
        mock_proc.stderr = ""

        entry = _make_entry(
            runtime="python",
            docker_image="node:18-slim",
            function_dir="/tmp/test",
            main_py_path="/tmp/test/main.py",
            manifest={},
        )

        with patch("core_runtime.capability_executor._DockerRunBuilder", mock_builder_cls), \
             patch("subprocess.run", return_value=mock_proc), \
             patch.object(executor, "_is_docker_available", return_value=True), \
             patch("os.unlink"), \
             patch("tempfile.NamedTemporaryFile") as mock_tmp:
            mock_tmp_file = MagicMock()
            mock_tmp_file.__enter__ = MagicMock(return_value=mock_tmp_file)
            mock_tmp_file.__exit__ = MagicMock(return_value=False)
            mock_tmp_file.name = "/tmp/fake_input.json"
            mock_tmp.return_value = mock_tmp_file

            # _execute_user_function_docker を直接呼ぶ
            executor._execute_user_function_docker(
                principal_id="user1",
                entry=entry,
                args={},
                request_id="req1",
                start_time=time.time(),
                timeout=30.0,
            )

            # builder.image() が "node:18-slim" で呼ばれたか確認
            mock_builder_instance.image.assert_called_once_with("node:18-slim")


# =====================================================================
# Wave 29: core function テーブル化テスト
# =====================================================================

class TestWave29_CoreFunctionTable:
    """core function handler テーブルのテスト。"""

    def _make_executor(self):
        from core_runtime.capability_executor import CapabilityExecutor
        executor = CapabilityExecutor()
        executor._initialized = True
        executor._core_function_handlers = {
            "core_docker_capability": "docker_capability_handler",
        }
        return executor

    def test_core_docker_resolves_from_table(self):
        """10. core_docker_capability → テーブルから docker_capability_handler を解決"""
        executor = self._make_executor()

        # テーブルのキーを直接確認
        di_service_name = executor._core_function_handlers.get("core_docker_capability")
        assert di_service_name == "docker_capability_handler"

    def test_unknown_core_pack_error(self):
        """11. 未登録の core pack → unknown_core_function エラー"""
        executor = self._make_executor()

        entry = _make_entry(
            pack_id="core_unknown_pack",
            function_id="some_func",
            manifest={},
        )

        resp = executor._dispatch_core_function(
            principal_id="user1",
            entry=entry,
            args={},
            request_id="req1",
            start_time=time.time(),
        )
        assert resp.success is False
        assert resp.error_type == "unknown_core_function"
        assert "core_unknown_pack" in resp.error

    def test_register_core_handler_dynamic(self):
        """12. register_core_handler で動的登録 → 解決できる"""
        executor = self._make_executor()

        # 未登録であることを確認
        assert executor._core_function_handlers.get("core_my_custom") is None

        # 動的登録
        executor.register_core_handler("core_my_custom", "my_custom_handler")

        # 登録確認
        assert executor._core_function_handlers.get("core_my_custom") == "my_custom_handler"


# =====================================================================
# Wave 30: extensions 検索テスト
# =====================================================================

class TestWave30_Extensions:
    """search_by_extension のテスト。"""

    def _make_registry_with_entries(self) -> FunctionRegistry:
        """テスト用レジストリを作る。"""
        reg = FunctionRegistry()

        # extensions あり: visual_editor namespace
        e1 = _make_entry(
            function_id="func_nlp",
            pack_id="pack_a",
            extensions={"visual_editor": {"category": "NLP", "version": "1.0"}},
        )
        # extensions あり: visual_editor namespace, category 異なる
        e2 = _make_entry(
            function_id="func_cv",
            pack_id="pack_b",
            extensions={"visual_editor": {"category": "CV", "version": "2.0"}},
        )
        # extensions あり: 別 namespace
        e3 = _make_entry(
            function_id="func_other",
            pack_id="pack_c",
            extensions={"analytics": {"metric": "latency"}},
        )
        # extensions なし
        e4 = _make_entry(
            function_id="func_plain",
            pack_id="pack_d",
        )

        reg.register(e1)
        reg.register(e2)
        reg.register(e3)
        reg.register(e4)
        return reg

    def test_search_by_namespace(self):
        """13. search_by_extension('visual_editor') — namespace でフィルタ"""
        reg = self._make_registry_with_entries()
        results = reg.search_by_extension("visual_editor")
        fids = {e.function_id for e in results}
        assert fids == {"func_nlp", "func_cv"}

    def test_search_by_namespace_key_value(self):
        """14. search_by_extension('visual_editor', key='category', value='NLP') — key+value フィルタ"""
        reg = self._make_registry_with_entries()
        results = reg.search_by_extension("visual_editor", key="category", value="NLP")
        assert len(results) == 1
        assert results[0].function_id == "func_nlp"

    def test_empty_extensions_not_matched(self):
        """15. extensions が空の FunctionEntry はヒットしない"""
        reg = self._make_registry_with_entries()
        results = reg.search_by_extension("visual_editor")
        fids = {e.function_id for e in results}
        assert "func_plain" not in fids
        assert "func_other" not in fids


# =====================================================================
# 追加テスト: エッジケース
# =====================================================================

class TestEdgeCases:
    """追加のエッジケースカバレッジ。"""

    def test_binary_not_found_returns_error(self):
        """binary パスが存在しない場合のエラー"""
        from core_runtime.capability_executor import CapabilityExecutor
        executor = CapabilityExecutor()
        executor._initialized = True
        executor._core_function_handlers = {}

        entry = _make_entry(
            runtime="binary",
            main_binary_path="/nonexistent/binary",
            function_dir="/tmp",
            manifest={},
        )
        resp = executor._execute_binary_function(
            principal_id="user1", entry=entry, args={},
            request_id="req1", start_time=time.time(),
        )
        assert resp.success is False
        assert resp.error_type == "binary_not_found"

    def test_command_empty_list_returns_error(self):
        """command が空リストの場合のエラー"""
        from core_runtime.capability_executor import CapabilityExecutor
        executor = CapabilityExecutor()
        executor._initialized = True
        executor._core_function_handlers = {}

        entry = _make_entry(
            runtime="command",
            command=[],
            function_dir="/tmp",
            manifest={},
        )
        resp = executor._execute_command_function(
            principal_id="user1", entry=entry, args={},
            request_id="req1", start_time=time.time(),
        )
        assert resp.success is False
        assert resp.error_type == "invalid_config"

    def test_host_execution_command_rejected(self):
        """host_execution=True + runtime='command' → security_violation"""
        from core_runtime.capability_executor import CapabilityExecutor
        executor = CapabilityExecutor()
        executor._initialized = True
        executor._core_function_handlers = {}

        entry = _make_entry(
            host_execution=True,
            runtime="command",
            command=["echo", "hello"],
            manifest={},
        )
        resp = executor._execute_user_function(
            principal_id="user1", entry=entry, args={},
            request_id="req1", start_time=time.time(),
        )
        assert resp.success is False
        assert resp.error_type == "security_violation"

    def test_search_by_extension_key_only(self):
        """search_by_extension で key のみ指定 (value=None)"""
        reg = FunctionRegistry()
        e1 = _make_entry(
            function_id="f1", pack_id="p1",
            extensions={"ns": {"k1": "v1", "k2": "v2"}},
        )
        e2 = _make_entry(
            function_id="f2", pack_id="p2",
            extensions={"ns": {"k2": "v3"}},
        )
        reg.register(e1)
        reg.register(e2)

        results = reg.search_by_extension("ns", key="k1")
        assert len(results) == 1
        assert results[0].function_id == "f1"

    def test_runtime_python_default_when_omitted(self, tmp_path):
        """manifest に runtime を指定しない場合 python がデフォルト"""
        func_dir = tmp_path / "func"
        func_dir.mkdir()
        (func_dir / "main.py").write_text("def run(ctx, args): pass")

        entry = FunctionRegistry._entry_from_kwargs(
            pack_id="pk", function_id="fn",
            manifest={},  # runtime キーなし
            function_dir=func_dir,
        )
        assert entry.runtime == "python"
        assert entry.main_py_path is not None
