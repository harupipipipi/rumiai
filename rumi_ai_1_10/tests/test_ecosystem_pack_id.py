"""
Tests for pack_id / pack_identity auto-complement logic in Registry._load_pack.

D-PATCH: ecosystem.json pack_id / pack_identity auto-complement
"""

import json
import logging
import os
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Minimal ecosystem data helpers
# ---------------------------------------------------------------------------

def _minimal_ecosystem(pack_id=None, pack_identity=None, version="1.0.0"):
    """Return a minimal ecosystem dict.

    Only *supplied* keys are included so that tests can exercise
    the auto-complement paths.
    """
    data = {
        "version": version,
        "vocabulary": {"types": ["example"]},
    }
    if pack_id is not None:
        data["pack_id"] = pack_id
    if pack_identity is not None:
        data["pack_identity"] = pack_identity
    return data


def _write_ecosystem(base_dir: Path, eco_data: dict) -> Path:
    """Write ecosystem.json into *base_dir* and return the file path."""
    base_dir.mkdir(parents=True, exist_ok=True)
    eco_file = base_dir / "ecosystem.json"
    eco_file.write_text(json.dumps(eco_data), encoding="utf-8")
    return eco_file


# ---------------------------------------------------------------------------
# Import Registry (with safe fallback)
# ---------------------------------------------------------------------------

def _import_registry():
    """Import Registry class; skip the test module if unavailable."""
    try:
        from backend_core.ecosystem.registry import Registry
        return Registry
    except ImportError:
        pytest.skip(
            "backend_core.ecosystem.registry is not importable in this environment"
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPackIdAutoComplement:
    """pack_id / pack_identity auto-complement behaviour."""

    def test_both_present_no_change(self, tmp_path, caplog):
        """pack_id and pack_identity both present -> no auto-complement."""
        Registry = _import_registry()

        eco_data = _minimal_ecosystem(
            pack_id="my_pack",
            pack_identity="github:author/my_pack",
        )
        pack_dir = tmp_path / "my_pack"
        _write_ecosystem(pack_dir, eco_data)

        registry = Registry(ecosystem_dir=tmp_path)

        with caplog.at_level(logging.DEBUG):
            info = registry._load_pack(pack_dir)

        assert info is not None
        assert info.pack_id == "my_pack"
        assert info.pack_identity == "github:author/my_pack"
        assert "pack_id auto-generated" not in caplog.text

    def test_pack_id_missing_github_identity(self, tmp_path, caplog):
        """pack_id missing + pack_identity='github:author/my_pack'
        -> pack_id='my_pack' auto-generated."""
        Registry = _import_registry()

        eco_data = _minimal_ecosystem(
            pack_identity="github:author/my_pack",
        )
        pack_dir = tmp_path / "test_pack"
        _write_ecosystem(pack_dir, eco_data)

        registry = Registry(ecosystem_dir=tmp_path)

        # validate_ecosystem rejects missing pack_id (required by schema).
        # Patch it to let auto-complement logic run.
        with patch(
            "backend_core.ecosystem.registry.validate_ecosystem"
        ) as mock_validate:
            mock_validate.return_value = []
            with caplog.at_level(logging.DEBUG):
                info = registry._load_pack(pack_dir)

        assert info is not None
        assert info.pack_id == "my_pack"
        assert "pack_id auto-generated" in caplog.text

    def test_pack_id_missing_local_identity(self, tmp_path, caplog):
        """pack_id missing + pack_identity='local:my_pack'
        -> pack_id='my_pack' auto-generated."""
        Registry = _import_registry()

        eco_data = _minimal_ecosystem(
            pack_identity="local:my_pack",
        )
        pack_dir = tmp_path / "test_pack"
        _write_ecosystem(pack_dir, eco_data)

        registry = Registry(ecosystem_dir=tmp_path)

        with patch(
            "backend_core.ecosystem.registry.validate_ecosystem"
        ) as mock_validate:
            mock_validate.return_value = []
            with caplog.at_level(logging.DEBUG):
                info = registry._load_pack(pack_dir)

        assert info is not None
        assert info.pack_id == "my_pack"
        assert "pack_id auto-generated" in caplog.text

    def test_pack_identity_missing_warns(self, tmp_path, caplog):
        """pack_id present + pack_identity missing -> warning logged."""
        Registry = _import_registry()

        # Write ecosystem with pack_id but pack_identity as empty string.
        # (Absent key would cause KeyError downstream; empty string
        #  exercises the warning branch without crashing.)
        eco_data = _minimal_ecosystem(
            pack_id="my_pack",
        )
        eco_data["pack_identity"] = ""
        pack_dir = tmp_path / "test_pack"
        _write_ecosystem(pack_dir, eco_data)

        registry = Registry(ecosystem_dir=tmp_path)

        with patch(
            "backend_core.ecosystem.registry.validate_ecosystem"
        ) as mock_validate:
            mock_validate.return_value = []
            with caplog.at_level(logging.WARNING):
                info = registry._load_pack(pack_dir)

        assert "pack_identity is missing" in caplog.text
