from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core_runtime.defaultspack_runtime import invoke_defaultspack_function
from core_runtime.function_registry import FunctionEntry


class _FakeFunctionRegistry:
    def __init__(self, entry):
        self._entry = entry

    def get(self, qualified_name):
        if qualified_name == self._entry.qualified_name:
            return self._entry
        return None


class _FakeContainer:
    def __init__(self, entry):
        self._registry = _FakeFunctionRegistry(entry)

    def get(self, name):
        if name == "function_registry":
            return self._registry
        raise KeyError(name)

    def get_or_none(self, name):
        if name == "function_registry":
            return self._registry
        return None


class TestDefaultspackRuntime(unittest.TestCase):
    def test_invoke_defaultspack_function_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            function_dir = Path(tmp)
            target = function_dir / "main.py"
            target.write_text(
                "def run(context, args):\n    return {'ok': True, 'args': args}\n",
                encoding="utf-8",
            )
            entry = FunctionEntry(
                function_id="demo",
                pack_id="defaultspack",
                function_dir=function_dir,
                entrypoint="main.py:run",
            )

            with patch("core_runtime.di_container.get_container", return_value=_FakeContainer(entry)):
                with patch(
                    "core_runtime.defaultspack_runtime.is_path_within",
                    return_value=False,
                ):
                    with self.assertRaises(PermissionError):
                        invoke_defaultspack_function("defaultspack:demo")


if __name__ == "__main__":
    unittest.main()
