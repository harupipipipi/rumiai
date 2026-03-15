"""
test_sec2_python_file_executor_image.py - SEC-2 Docker image ダイジェスト固定テスト

対象: core_runtime/python_file_executor.py
検証: DEFAULT_EXECUTOR_IMAGE / EXECUTOR_IMAGE 定数と環境変数上書き
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


class TestDefaultExecutorImage:
    """DEFAULT_EXECUTOR_IMAGE 定数のテスト"""

    def test_default_executor_image_has_digest(self):
        """DEFAULT_EXECUTOR_IMAGE に sha256 ダイジェストが含まれる"""
        from core_runtime.python_file_executor import DEFAULT_EXECUTOR_IMAGE

        assert "python:3.11-slim@sha256:" in DEFAULT_EXECUTOR_IMAGE
        # sha256: の後に64文字の16進数が続く
        digest_part = DEFAULT_EXECUTOR_IMAGE.split("@sha256:")[1]
        assert len(digest_part) == 64
        assert all(c in "0123456789abcdef" for c in digest_part)

    def test_executor_image_equals_default(self):
        """環境変数未設定時、EXECUTOR_IMAGE == DEFAULT_EXECUTOR_IMAGE"""
        from core_runtime.python_file_executor import (
            DEFAULT_EXECUTOR_IMAGE,
            EXECUTOR_IMAGE,
        )

        # 環境変数 RUMI_EXECUTOR_IMAGE が未設定の場合
        if "RUMI_EXECUTOR_IMAGE" not in os.environ:
            assert EXECUTOR_IMAGE == DEFAULT_EXECUTOR_IMAGE


class TestExecutorImageEnvOverride:
    """RUMI_EXECUTOR_IMAGE 環境変数による上書きテスト"""

    def test_executor_image_env_override(self, monkeypatch):
        """RUMI_EXECUTOR_IMAGE 設定後にモジュールリロードすると EXECUTOR_IMAGE が変わる"""
        custom_image = (
            "my-registry.example.com/python:3.11-custom@sha256:"
            "abcd1234abcd1234abcd1234abcd1234abcd1234abcd1234abcd1234abcd1234"
        )
        monkeypatch.setenv("RUMI_EXECUTOR_IMAGE", custom_image)

        import core_runtime.python_file_executor as pfe_module
        importlib.reload(pfe_module)

        assert pfe_module.EXECUTOR_IMAGE == custom_image
        # DEFAULT は変わらない
        assert "python:3.11-slim@sha256:" in pfe_module.DEFAULT_EXECUTOR_IMAGE

    def test_executor_image_env_empty_uses_default(self, monkeypatch):
        """RUMI_EXECUTOR_IMAGE が空文字列の場合、os.environ.get の仕様で空文字列が返る"""
        monkeypatch.setenv("RUMI_EXECUTOR_IMAGE", "")

        import core_runtime.python_file_executor as pfe_module
        importlib.reload(pfe_module)

        # os.environ.get は空文字列もキーが存在する扱い → 空文字列が返る
        assert pfe_module.EXECUTOR_IMAGE == ""


class TestExecutorImageUsedInContainerCommand:
    """_execute_in_container が EXECUTOR_IMAGE を builder.image() に渡すことの検証"""

    def test_executor_image_used_in_container_command(self, monkeypatch):
        """DockerRunBuilder.image() に EXECUTOR_IMAGE の値が渡される"""
        from core_runtime.python_file_executor import (
            PythonFileExecutor,
            ExecutionContext,
            EXECUTOR_IMAGE,
        )

        executor = PythonFileExecutor()

        # approval_checker mock（承認済み）
        mock_approval = MagicMock()
        mock_approval.is_approved.return_value = (True, None)
        mock_approval.verify_hash.return_value = (True, None)
        executor._approval_checker = mock_approval

        # path_validator mock
        resolved_path = Path("/fake/ecosystem/test_pack/run.py")
        mock_validator = MagicMock()
        mock_validator.validate.return_value = (True, None, resolved_path)
        executor._path_validator = mock_validator

        ctx = ExecutionContext(
            flow_id="test_flow",
            step_id="test_step",
            phase="startup",
            ts="2025-01-01T00:00:00Z",
            owner_pack="test_pack",
            inputs={},
        )

        captured_image = {}

        class FakeBuilder:
            """DockerRunBuilder の最小スタブ"""
            def __init__(self, **kwargs):
                pass
            def pids_limit(self, n):
                pass
            def volume(self, v):
                pass
            def env(self, k, v):
                pass
            def group_add(self, g):
                pass
            def workdir(self, w):
                pass
            def label(self, k, v):
                pass
            def image(self, img):
                captured_image["value"] = img
            def command(self, cmd):
                pass
            def build(self):
                return ["echo", "fake"]

        monkeypatch.setattr(
            "core_runtime.python_file_executor.DockerRunBuilder",
            FakeBuilder,
        )

        # subprocess.Popen をモック（Docker実行を回避）
        mock_popen = MagicMock()
        mock_popen.return_value.stdout.read.return_value = b'{"ok": true}'
        mock_popen.return_value.stderr.read.return_value = b""
        mock_popen.return_value.returncode = 0
        mock_popen.return_value.wait.return_value = 0
        mock_popen.return_value.poll.return_value = 0

        monkeypatch.setattr("subprocess.Popen", mock_popen)

        # tempfile 削除をスキップ（ファイルが実在しなくても安全に）
        original_unlink = os.unlink

        def safe_unlink(path):
            try:
                original_unlink(path)
            except OSError:
                pass

        monkeypatch.setattr("os.unlink", safe_unlink)

        result = executor._execute_in_container(
            file_path=resolved_path,
            owner_pack="test_pack",
            input_data={"key": "val"},
            context=ctx,
            timeout_seconds=30.0,
        )

        assert "value" in captured_image, "builder.image() was not called"
        assert captured_image["value"] == EXECUTOR_IMAGE
