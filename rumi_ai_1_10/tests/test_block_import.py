"""test_block_import.py — _generate_executor_script の /workspace sys.path テスト"""
import unittest


class TestBlockImport(unittest.TestCase):
    """_generate_executor_script が /workspace を sys.path に含むことを確認"""

    def test_workspace_in_syspath(self):
        """生成スクリプトに sys.path.insert(0, "/workspace") が含まれること"""
        from rumi_ai_1_10.core_runtime.python_file_executor import PythonFileExecutor
        executor = PythonFileExecutor()
        script = executor._generate_executor_script("dummy.py")
        self.assertIn('sys.path.insert(0, "/workspace")', script)

    def test_root_still_in_syspath(self):
        """既存の sys.path.insert(0, "/") が維持されていること"""
        from rumi_ai_1_10.core_runtime.python_file_executor import PythonFileExecutor
        executor = PythonFileExecutor()
        script = executor._generate_executor_script("dummy.py")
        self.assertIn('sys.path.insert(0, "/")', script)

    def test_workspace_after_root(self):
        """/workspace の挿入が "/" の後にあること"""
        from rumi_ai_1_10.core_runtime.python_file_executor import PythonFileExecutor
        executor = PythonFileExecutor()
        script = executor._generate_executor_script("dummy.py")
        root_pos = script.index('sys.path.insert(0, "/")')
        workspace_pos = script.index('sys.path.insert(0, "/workspace")')
        self.assertGreater(workspace_pos, root_pos)


if __name__ == "__main__":
    unittest.main()
