"""
W19-F  VULN-M05 -- JSON file-size limit guard
===============================================
Tests for ``_check_json_file_size`` and ``RUMI_MAX_JSON_FILE_BYTES``
in ``backend_core.ecosystem.registry``.
"""
from __future__ import annotations

import importlib.util
import logging
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Bootstrap: stub every relative-import dependency so registry.py can load
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
for _m in _STUBS:
    if _m not in sys.modules:
        sys.modules[_m] = MagicMock()

_eco = sys.modules["backend_core.ecosystem"]
_eco.__path__ = []
_eco.__package__ = "backend_core.ecosystem"

class _SVE(Exception):
    pass

_val = sys.modules["backend_core.ecosystem.spec.schema.validator"]
_val.SchemaValidationError = _SVE
_val.validate_ecosystem = MagicMock()
_val.validate_component_manifest = MagicMock()
_val.validate_addon = MagicMock()

_REG_PY = (
    Path(__file__).resolve().parent.parent
    / "backend_core" / "ecosystem" / "registry.py"
)


def _load_registry():
    """(Re-)load registry.py from disk."""
    spec = importlib.util.spec_from_file_location(
        "backend_core.ecosystem.registry",
        str(_REG_PY),
        submodule_search_locations=[],
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_reg = _load_registry()

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_file(tmp_path: Path, size: int) -> Path:
    """Create a file of exactly *size* bytes."""
    fp = tmp_path / "test.json"
    if size == 0:
        fp.write_bytes(b"")
    else:
        base = '{"k": ""}'          # 10 bytes
        if size < len(base):
            fp.write_bytes(b"x" * size)
        else:
            fp.write_text(
                '{"k": "' + "a" * (size - len(base)) + '"}',
                encoding="utf-8",
            )
    assert fp.stat().st_size == size
    return fp


# ---------------------------------------------------------------------------
# Test cases  (8 >= required 5)
# ---------------------------------------------------------------------------

class TestCheckJsonFileSize:

    def test_normal_size_allows_load(self, tmp_path):
        """TC-1: Normal-size file -> skip=False (load OK)."""
        fp = _make_file(tmp_path, 1024)
        assert _reg._check_json_file_size(fp) is False

    def test_oversized_warns_and_skips(self, tmp_path, caplog):
        """TC-2: Oversized file -> WARNING + skip=True."""
        fp = _make_file(tmp_path, 600)
        with caplog.at_level(logging.WARNING):
            result = _reg._check_json_file_size(fp, max_bytes=500)
        assert result is True
        assert "exceeds limit" in caplog.text

    def test_custom_env_var(self, tmp_path, monkeypatch):
        """TC-3: Custom RUMI_MAX_JSON_FILE_BYTES env var is respected."""
        monkeypatch.setenv("RUMI_MAX_JSON_FILE_BYTES", "256")
        mod = _load_registry()
        assert mod.RUMI_MAX_JSON_FILE_BYTES == 256

        fp_ok = _make_file(tmp_path, 256)
        assert mod._check_json_file_size(fp_ok) is False

        sub = tmp_path / "over"
        sub.mkdir()
        fp_ng = _make_file(sub, 257)
        assert mod._check_json_file_size(fp_ng) is True

    def test_zero_byte_file(self, tmp_path, caplog):
        """TC-4: 0-byte file -> size check passes (skip=False)."""
        fp = _make_file(tmp_path, 0)
        with caplog.at_level(logging.WARNING):
            result = _reg._check_json_file_size(fp)
        assert result is False
        assert "exceeds limit" not in caplog.text

    def test_exact_limit_allows_load(self, tmp_path):
        """TC-5: File size == limit -> skip=False (boundary OK)."""
        fp = _make_file(tmp_path, 2048)
        assert _reg._check_json_file_size(fp, max_bytes=2048) is False

    def test_nonexistent_file_skips(self, tmp_path, caplog):
        """TC-6: Non-existent file -> skip=True + WARNING."""
        fp = tmp_path / "ghost.json"
        with caplog.at_level(logging.WARNING):
            result = _reg._check_json_file_size(fp)
        assert result is True
        assert "Cannot stat" in caplog.text

    def test_one_byte_over(self, tmp_path):
        """TC-7: limit + 1 byte -> skip=True."""
        fp = _make_file(tmp_path, 1001)
        assert _reg._check_json_file_size(fp, max_bytes=1000) is True

    def test_default_limit_is_2mb(self):
        """TC-8: Default limit = 2 097 152 (2 MB)."""
        assert _reg.RUMI_MAX_JSON_FILE_BYTES == 2097152
