"""test_async_streaming.py — async/streaming 対応テスト"""
import inspect
import unittest


class TestExecutionResultIsStreaming(unittest.TestCase):
    """ExecutionResult.is_streaming フィールドのテスト"""

    def test_is_streaming_default_false(self):
        """is_streaming のデフォルト値が False であること"""
        from rumi_ai_1_10.core_runtime.python_file_executor import ExecutionResult
        result = ExecutionResult(success=True)
        self.assertFalse(result.is_streaming)

    def test_is_streaming_can_be_set_true(self):
        """is_streaming を True に設定できること"""
        from rumi_ai_1_10.core_runtime.python_file_executor import ExecutionResult
        result = ExecutionResult(success=True, is_streaming=True)
        self.assertTrue(result.is_streaming)


class TestGeneratorDetection(unittest.TestCase):
    """ジェネレータ関数の検出テスト"""

    def test_generator_function_detected(self):
        """inspect.isgeneratorfunction でジェネレータ関数を検出できること"""
        def my_generator():
            yield 1
            yield 2
        self.assertTrue(inspect.isgeneratorfunction(my_generator))

    def test_normal_function_not_generator(self):
        """通常関数はジェネレータとして検出されないこと"""
        def my_func():
            return 1
        self.assertFalse(inspect.isgeneratorfunction(my_func))


class TestAsyncDetection(unittest.TestCase):
    """async関数の検出テスト"""

    def test_async_function_detected(self):
        """inspect.iscoroutinefunction で async 関数を検出できること"""
        async def my_async():
            return 1
        self.assertTrue(inspect.iscoroutinefunction(my_async))

    def test_normal_function_not_async(self):
        """通常関数は async として検出されないこと"""
        def my_func():
            return 1
        self.assertFalse(inspect.iscoroutinefunction(my_func))


if __name__ == "__main__":
    unittest.main()
