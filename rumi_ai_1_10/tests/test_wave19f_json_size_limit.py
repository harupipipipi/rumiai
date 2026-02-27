"""
W19-F  VULN-M05 — JSON file-size limit guard
=============================================
Tests for ``_check_json_file_size`` and the ``RUMI_MAX_JSON_FILE_BYTES``
environment-variable mechanism added to ``backend_core.ecosystem.registry``.
"""
from __future__ import annotations

import importlib
import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Bootstrap: stub every relative-import dependency so that registry.py
# can be loaded in isolation.
# ---------------------------------------------------------------------------
_STUBS = [
    "backend_core",
    "backend_core.ecosystem",
    "backend_core.ecosystem.uuid_utils",
    "backend_core.ecosystem.json_patch",
    "backend_core.ecosystem.spec",
    "backend_core.ecosystem.spec.schema",
    "backend_core.ecosystem.spec.schema.validator",
    "core_runtime",
    "core_runtime.paths",
]

# Keep a reference so we can restore later if needed
_saved: dict = {}
for _m in _STUBS:
    _saved[_m] = sys.modules.get(_m)
    if _m not in sys.modules:
        sys.modules[_m] = MagicMock()

# Make the ecosystem stub look like a real package for relative imports
_eco_stub = sys.modules["backend_core.ecosystem"]
_eco_stub.__path__ = []
_eco_stub.__package__ = "backend_core.ecosystem"

# SchemaValidationError must be an actual exception class for `except` clauses
class _StubSchemaValidationError(Exception):
    pass

_validator_stub = sys.modules["backend_core.ecosystem.spec.schema.validator"]
_validator_stub.SchemaValidationError = _StubSchemaValidationError
_validator_stub.validate_ecosystem = MagicMock()
_validator_stub.validate_component_manifest = MagicMock()
_validator_stub.validate_addon = MagicMock()

# Ensure the project root is on sys.path
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Now import the real module
import importlib.util as _ilu

_spec = _ilu.spec_from_file_location(
    "backend_core.ecosystem.registry",
    str(Path(__file__).resolve().parent.parent / "backend_core" / "ecosystem" / "registry.py"),
    submodule_search_locations=[],
)
registry_mod = _ilu.module_from_spec(_spec)
sys.modules[_spec.name] = registry_mod
_spec.loader.exec_module(registry_mod)

_check_json_file_size = registry_mod._check_json_file_size
RUMI_MAX_JSON_FILE_BYTES = registry_mod.RUMI_MAX_JSON_FILE_BYTES

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_json_file(tmp_path: Path, size_bytes: int, *, content: str | None = None) -> Path:
    """Create a temporary JSON file of *exactly* ``size_bytes``."""
    fp = tmp_path / "test.json"
    if content is not None:
        fp.write_text(content, encoding="utf-8")
        return fp
    # Build a JSON payload that is exactly size_bytes long.
    # Strategy: '{"k": "<padding>"}' — adjust padding to hit target size.
    if size_bytes == 0:
        fp.write_bytes(b"")
        return fp
    shell = '{"k": ""}'  # 10 bytes
    if size_bytes < len(shell):
        # Too small for valid JSON — just write raw bytes
        fp.write_bytes(b"x" * size_bytes)
        return fp
    padding_len = size_bytes - len(shell)
    payload = '{"k": "' + ("a" * padding_len) + '"}'
    fp.write_text(payload, encoding="utf-8")
    assert fp.stat().st_size == size_bytes, f"expected {size_bytes}, got {fp.stat().st_size}"
    return fp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCheckJsonFileSize:
    """Unit tests for _check_json_file_size."""

    def test_normal_size_returns_false(self, tmp_path: Path):
        """正常サイズの JSON → skip=False (読み込み許可)"""
        fp = _make_json_file(tmp_path, 1024)
        assert _check_json_file_size(fp) is False

    def test_oversized_returns_true_with_warning(self, tmp_path: Path, caplog):
        """上限超過の JSON → WARNING + skip=True"""
        limit = 512
        fp = _make_json_file(tmp_path, limit + 1)
        with caplog.at_level(logging.WARNING):
            result = _check_json_file_size(fp, max_bytes=limit)
        assert result is True
        assert "exceeds limit" in caplog.text

    def test_custom_env_var(self, tmp_path: Path, monkeypatch):
        """RUMI_MAX_JSON_FILE_BYTES カスタム値 → 動作"""
        custom_limit = 256
        monkeypatch.setenv("RUMI_MAX_JSON_FILE_BYTES", str(custom_limit))
        # Re-evaluate the module-level constant by reloading
        importlib.reload(registry_mod)
        reloaded_check = registry_mod._check_json_file_size
        reloaded_limit = registry_mod.RUMI_MAX_JSON_FILE_BYTES

        assert reloaded_limit == custom_limit

        fp_ok = _make_json_file(tmp_path, custom_limit)
        assert reloaded_check(fp_ok) is False

        fp_over = _make_json_file(tmp_path / "sub", 0)
        (tmp_path / "sub").mkdir(exist_ok=True)
        fp_over = _make_json_file(tmp_path / "sub", custom_limit + 1)
        assert reloaded_check(fp_over) is True

        # Restore default
        monkeypatch.delenv("RUMI_MAX_JSON_FILE_BYTES", raising=False)
        importlib.reload(registry_mod)

    def test_zero_byte_file(self, tmp_path: Path, caplog):
        """0 バイトの JSON → サイズチェック通過 (skip=False) — JSONパースは別責務"""
        fp = _make_json_file(tmp_path, 0)
        assert fp.stat().st_size == 0
        with caplog.at_level(logging.WARNING):
            result = _check_json_file_size(fp)
        assert result is False
        # No size-related warning should be emitted
        assert "exceeds limit" not in caplog.text

    def test_exact_limit_returns_false(self, tmp_path: Path):
        """上限ちょうどの JSON → skip=False (正常読み込み)"""
        limit = 2048
        fp = _make_json_file(tmp_path, limit)
        assert fp.stat().st_size == limit
        assert _check_json_file_size(fp, max_bytes=limit) is False

    def test_nonexistent_file_returns_true_with_warning(self, tmp_path: Path, caplog):
        """存在しないファイル → skip=True + WARNING"""
        fp = tmp_path / "does_not_exist.json"
        with caplog.at_level(logging.WARNING):
            result = _check_json_file_size(fp)
        assert result is True
        assert "Cannot stat" in caplog.text

    def test_one_byte_over_limit(self, tmp_path: Path):
        """上限+1バイト → skip=True"""
        limit = 1000
        fp = _make_json_file(tmp_path, limit + 1)
        assert _check_json_file_size(fp, max_bytes=limit) is True

    def test_default_limit_is_2mb(self):
        """デフォルト上限が 2097152 (2 MB) であること"""
        assert RUMI_MAX_JSON_FILE_BYTES == 2097152
