"""
test_vocab_lazy_load.py - [F] vocab lazy load tests

Tests for ComponentLifecycleExecutor._should_load_vocab():
  1. uses_vocab=True  -> returns True (load vocab)
  2. uses_vocab=False -> returns False (skip vocab)
  3. uses_vocab unset + vocab.txt exists -> returns True
  4. uses_vocab unset + no vocab files  -> returns False
  5. _read_ecosystem_data raises -> returns True (safe-side fallback)
  6. uses_vocab unset + converters dir exists -> returns True
"""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


class TestShouldLoadVocab(unittest.TestCase):
    """_should_load_vocab method unit tests."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.pack_subdir = Path(self.tmp_dir) / "my_pack"
        self.pack_subdir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _make_executor(self):
        """Create a ComponentLifecycleExecutor for testing."""
        from core_runtime.component_lifecycle import ComponentLifecycleExecutor

        diag = MagicMock()
        journal = MagicMock()
        return ComponentLifecycleExecutor(diagnostics=diag, install_journal=journal)

    # ------------------------------------------------------------------
    # Test 1: uses_vocab=True -> load
    # ------------------------------------------------------------------
    @patch("core_runtime.approval_manager.get_approval_manager")
    def test_uses_vocab_true(self, mock_get_am):
        am = MagicMock()
        am._read_ecosystem_data.return_value = {"uses_vocab": True}
        mock_get_am.return_value = am

        executor = self._make_executor()
        result = executor._should_load_vocab("test_pack", self.pack_subdir)
        self.assertTrue(result)

    # ------------------------------------------------------------------
    # Test 2: uses_vocab=False -> skip
    # ------------------------------------------------------------------
    @patch("core_runtime.approval_manager.get_approval_manager")
    def test_uses_vocab_false(self, mock_get_am):
        am = MagicMock()
        am._read_ecosystem_data.return_value = {"uses_vocab": False}
        mock_get_am.return_value = am

        executor = self._make_executor()
        result = executor._should_load_vocab("test_pack", self.pack_subdir)
        self.assertFalse(result)

    # ------------------------------------------------------------------
    # Test 3: uses_vocab unset + vocab.txt exists -> load
    # ------------------------------------------------------------------
    @patch("core_runtime.approval_manager.get_approval_manager")
    def test_uses_vocab_unset_with_vocab_file(self, mock_get_am):
        am = MagicMock()
        am._read_ecosystem_data.return_value = {}
        mock_get_am.return_value = am

        (self.pack_subdir / "vocab.txt").touch()

        executor = self._make_executor()
        result = executor._should_load_vocab("test_pack", self.pack_subdir)
        self.assertTrue(result)

    # ------------------------------------------------------------------
    # Test 4: uses_vocab unset + no vocab files -> skip
    # ------------------------------------------------------------------
    @patch("core_runtime.approval_manager.get_approval_manager")
    def test_uses_vocab_unset_no_files(self, mock_get_am):
        am = MagicMock()
        am._read_ecosystem_data.return_value = {}
        mock_get_am.return_value = am

        executor = self._make_executor()
        result = executor._should_load_vocab("test_pack", self.pack_subdir)
        self.assertFalse(result)

    # ------------------------------------------------------------------
    # Test 5: _read_ecosystem_data raises -> safe-side fallback (load)
    # ------------------------------------------------------------------
    @patch("core_runtime.approval_manager.get_approval_manager")
    def test_ecosystem_read_exception(self, mock_get_am):
        am = MagicMock()
        am._read_ecosystem_data.side_effect = RuntimeError("read failed")
        mock_get_am.return_value = am

        executor = self._make_executor()
        result = executor._should_load_vocab("test_pack", self.pack_subdir)
        self.assertTrue(result)

    # ------------------------------------------------------------------
    # Test 6: uses_vocab unset + converters dir exists -> load
    # ------------------------------------------------------------------
    @patch("core_runtime.approval_manager.get_approval_manager")
    def test_uses_vocab_unset_with_converters_dir(self, mock_get_am):
        am = MagicMock()
        am._read_ecosystem_data.return_value = {}
        mock_get_am.return_value = am

        (self.pack_subdir / "converters").mkdir()

        executor = self._make_executor()
        result = executor._should_load_vocab("test_pack", self.pack_subdir)
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
