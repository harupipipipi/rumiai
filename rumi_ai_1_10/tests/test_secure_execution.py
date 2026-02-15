"""
セキュア実行のテスト

strict/permissive モードでの実行挙動をテストする。
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# テスト対象のモジュールをインポート
sys.path.insert(0, str(Path(__file__).parent.parent))

from core_runtime.python_file_executor import (
    PythonFileExecutor,
    ExecutionContext,
    ExecutionResult,
    reset_python_file_executor,
)


class TestSecureExecution(unittest.TestCase):
    """セキュア実行のテスト"""
    
    def setUp(self):
        """テスト前の準備"""
        self.original_security_mode = os.environ.get("RUMI_SECURITY_MODE")
        reset_python_file_executor()
    
    def tearDown(self):
        """テスト後のクリーンアップ"""
        if self.original_security_mode:
            os.environ["RUMI_SECURITY_MODE"] = self.original_security_mode
        elif "RUMI_SECURITY_MODE" in os.environ:
            del os.environ["RUMI_SECURITY_MODE"]
        reset_python_file_executor()
    
    def _create_test_context(self) -> ExecutionContext:
        """テスト用のExecutionContextを作成"""
        return ExecutionContext(
            flow_id="test_flow",
            step_id="test_step",
            phase="test",
            ts="2024-01-01T00:00:00Z",
            owner_pack="test_pack",
            inputs={},
        )
    
    def test_strict_mode_docker_unavailable_rejects(self):
        """strict モードで Docker 不可の場合、拒否される"""
        os.environ["RUMI_SECURITY_MODE"] = "strict"
        executor = PythonFileExecutor()
        
        # Docker不可をモック
        with patch.object(executor, '_check_docker_available', return_value=False):
            # 承認チェックをパス
            with patch.object(executor._approval_checker, 'is_approved', return_value=(True, None)):
                with patch.object(executor._approval_checker, 'verify_hash', return_value=(True, None)):
                    # パス検証をパス（テスト用に許可パスを追加）
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                        f.write("def run(input_data): return {'result': 'test'}")
                        test_file = f.name
                    
                    try:
                        executor._path_validator.add_allowed_root(str(Path(test_file).parent))
                        
                        context = self._create_test_context()
                        result = executor.execute(
                            file_path=test_file,
                            owner_pack="test_pack",
                            input_data={},
                            context=context,
                            timeout_seconds=10.0
                        )
                        
                        # rejected であることを確認
                        self.assertFalse(result.success)
                        self.assertEqual(result.execution_mode, "rejected")
                        self.assertIn("Docker is required", result.error)
                    finally:
                        os.unlink(test_file)
    
    def test_permissive_mode_docker_unavailable_executes_with_warning(self):
        """permissive モードで Docker 不可の場合、警告付きで実行される"""
        os.environ["RUMI_SECURITY_MODE"] = "permissive"
        executor = PythonFileExecutor()
        
        # Docker不可をモック
        with patch.object(executor, '_check_docker_available', return_value=False):
            # 承認チェックをパス
            with patch.object(executor._approval_checker, 'is_approved', return_value=(True, None)):
                with patch.object(executor._approval_checker, 'verify_hash', return_value=(True, None)):
                    # テストファイルを作成
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                        f.write("def run(input_data, context=None): return {'result': 'test_output'}")
                        test_file = f.name
                    
                    try:
                        executor._path_validator.add_allowed_root(str(Path(test_file).parent))
                        
                        context = self._create_test_context()
                        result = executor.execute(
                            file_path=test_file,
                            owner_pack="test_pack",
                            input_data={},
                            context=context,
                            timeout_seconds=10.0
                        )
                        
                        # 実行成功だが警告付き
                        self.assertTrue(result.success)
                        self.assertEqual(result.execution_mode, "host_permissive")
                        self.assertTrue(len(result.warnings) > 0)
                        self.assertTrue(any("SECURITY WARNING" in w for w in result.warnings))
                    finally:
                        os.unlink(test_file)
    
    def test_unapproved_pack_rejected(self):
        """未承認のPackは拒否される"""
        os.environ["RUMI_SECURITY_MODE"] = "permissive"
        executor = PythonFileExecutor()
        
        # 承認チェックで拒否
        with patch.object(executor._approval_checker, 'is_approved', return_value=(False, "Pack not approved")):
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write("def run(input_data): return {'result': 'test'}")
                test_file = f.name
            
            try:
                executor._path_validator.add_allowed_root(str(Path(test_file).parent))
                
                context = self._create_test_context()
                result = executor.execute(
                    file_path=test_file,
                    owner_pack="unapproved_pack",
                    input_data={},
                    context=context,
                    timeout_seconds=10.0
                )
                
                # rejected であることを確認
                self.assertFalse(result.success)
                self.assertEqual(result.execution_mode, "rejected")
                self.assertEqual(result.error_type, "approval_rejected")
            finally:
                os.unlink(test_file)
    
    def test_execution_modes_are_clear(self):
        """実行モードが明確であること（container_stub は存在しない）"""
        valid_modes = {"container", "host_permissive", "rejected"}
        
        # ExecutionResult の execution_mode のデフォルト値を確認
        result = ExecutionResult(success=True)
        # デフォルトは "unknown" だが、実際の実行では上記3つのいずれかになる
        
        # container_stub が使われていないことを確認（コード検索的なテスト）
        import core_runtime.python_file_executor as pfe_module
        import inspect
        source = inspect.getsource(pfe_module)
        self.assertNotIn("container_stub", source)


class TestDockerExecution(unittest.TestCase):
    """Docker実行のテスト（Dockerが利用可能な環境でのみ実行）"""
    
    docker_available = False
    
    @classmethod
    def setUpClass(cls):
        """Dockerが利用可能か確認"""
        import subprocess
        try:
            result = subprocess.run(["docker", "info"], capture_output=True, timeout=10)
            cls.docker_available = result.returncode == 0
        except Exception:
            cls.docker_available = False
    
    def setUp(self):
        self.original_security_mode = os.environ.get("RUMI_SECURITY_MODE")
        os.environ["RUMI_SECURITY_MODE"] = "strict"
        reset_python_file_executor()
    
    def tearDown(self):
        if self.original_security_mode:
            os.environ["RUMI_SECURITY_MODE"] = self.original_security_mode
        elif "RUMI_SECURITY_MODE" in os.environ:
            del os.environ["RUMI_SECURITY_MODE"]
        reset_python_file_executor()
    
    def test_docker_execution_succeeds(self):
        """Docker実行が成功すること"""
        if not self.docker_available:
            self.skipTest("Docker not available")
        
        executor = PythonFileExecutor()
        
        # 承認チェックをパス
        with patch.object(executor._approval_checker, 'is_approved', return_value=(True, None)):
            with patch.object(executor._approval_checker, 'verify_hash', return_value=(True, None)):
                with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                    f.write("def run(input_data, context=None): return {'result': 'docker_test'}")
                    test_file = f.name
                
                try:
                    executor._path_validator.add_allowed_root(str(Path(test_file).parent))
                    
                    context = ExecutionContext(
                        flow_id="test_flow",
                        step_id="test_step",
                        phase="test",
                        ts="2024-01-01T00:00:00Z",
                        owner_pack="test_pack",
                        inputs={},
                    )
                    
                    result = executor.execute(
                        file_path=test_file,
                        owner_pack="test_pack",
                        input_data={"key": "value"},
                        context=context,
                        timeout_seconds=30.0
                    )
                    
                    self.assertTrue(result.success)
                    self.assertEqual(result.execution_mode, "container")
                finally:
                    os.unlink(test_file)


if __name__ == "__main__":
    unittest.main()
