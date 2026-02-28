"""Tests for W22-C: core_pack directory structure and Docker Capability handler."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CORE_PACK_DIR = _PROJECT_ROOT / "core_runtime" / "core_pack" / "core_docker_capability"
_ECOSYSTEM_JSON = _CORE_PACK_DIR / "ecosystem.json"
_HANDLER_DIR = _CORE_PACK_DIR / "share" / "capability_handlers" / "docker_run"
_HANDLER_JSON = _HANDLER_DIR / "handler.json"
_HANDLER_PY = _HANDLER_DIR / "handler.py"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _load_json(path: Path) -> dict:
    """Load and parse a JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


def _import_handler_module():
    """Dynamically import handler.py without relying on package structure."""
    spec = importlib.util.spec_from_file_location("docker_run_handler", str(_HANDLER_PY))
    mod = importlib.util.module_from_spec(spec)
    # Ensure core_runtime stub exists so the try-except in handler.py works
    if "core_runtime" not in sys.modules:
        import types
        pkg = types.ModuleType("core_runtime")
        pkg.__path__ = [str(_PROJECT_ROOT / "core_runtime")]
        pkg.__package__ = "core_runtime"
        sys.modules["core_runtime"] = pkg
    spec.loader.exec_module(mod)
    return mod


# ===========================================================================
# ecosystem.json tests
# ===========================================================================

class TestEcosystemJson:
    """Validate ecosystem.json for core_docker_capability."""

    def test_ecosystem_json_is_valid_json(self) -> None:
        """ecosystem.json must be valid JSON."""
        data = _load_json(_ECOSYSTEM_JSON)
        assert isinstance(data, dict)

    def test_ecosystem_json_has_required_fields(self) -> None:
        """ecosystem.json must contain pack_id, pack_identity, version, vocabulary."""
        data = _load_json(_ECOSYSTEM_JSON)
        for field in ("pack_id", "pack_identity", "version", "vocabulary"):
            assert field in data, f"Missing required field: {field}"

    def test_ecosystem_pack_id_has_core_prefix(self) -> None:
        """pack_id must start with core_."""
        data = _load_json(_ECOSYSTEM_JSON)
        assert data["pack_id"].startswith("core_"), (
            f"pack_id must have core_ prefix, got: {data['pack_id']}"
        )

    def test_ecosystem_pack_identity_starts_with_core(self) -> None:
        """pack_identity must start with core:."""
        data = _load_json(_ECOSYSTEM_JSON)
        assert data["pack_identity"].startswith("core:"), (
            f"pack_identity must start with core:, got: {data['pack_identity']}"
        )

    def test_ecosystem_metadata_is_core_pack(self) -> None:
        """metadata.is_core_pack must be true."""
        data = _load_json(_ECOSYSTEM_JSON)
        assert "metadata" in data
        assert data["metadata"].get("is_core_pack") is True


# ===========================================================================
# handler.json tests
# ===========================================================================

class TestHandlerJson:
    """Validate handler.json for docker_run."""

    def test_handler_json_is_valid_json(self) -> None:
        """handler.json must be valid JSON."""
        data = _load_json(_HANDLER_JSON)
        assert isinstance(data, dict)

    def test_handler_json_has_required_fields(self) -> None:
        """handler.json must contain handler_id, permission_id, entrypoint, risk."""
        data = _load_json(_HANDLER_JSON)
        for field in ("handler_id", "permission_id", "entrypoint", "risk"):
            assert field in data, f"Missing required field: {field}"

    def test_handler_json_permission_id(self) -> None:
        """permission_id must be docker.run."""
        data = _load_json(_HANDLER_JSON)
        assert data["permission_id"] == "docker.run"

    def test_handler_json_input_schema_required(self) -> None:
        """input_schema.required must contain image and command."""
        data = _load_json(_HANDLER_JSON)
        required = data["input_schema"]["required"]
        assert "image" in required, "image must be in required"
        assert "command" in required, "command must be in required"


# ===========================================================================
# handler.py tests
# ===========================================================================

class TestHandlerPy:
    """Validate handler.py for docker_run."""

    def test_handler_py_exists_and_has_execute(self) -> None:
        """handler.py must exist and define an execute function."""
        assert _HANDLER_PY.exists(), f"handler.py not found at {_HANDLER_PY}"
        mod = _import_handler_module()
        assert hasattr(mod, "execute"), "handler.py must define execute()"
        assert callable(mod.execute)

    def test_handler_py_returns_error_without_dependency(self) -> None:
        """execute() must return error when DockerCapabilityHandler is unavailable."""
        mod = _import_handler_module()
        # Force DockerCapabilityHandler to None (simulating missing W22-D)
        mod.DockerCapabilityHandler = None
        result = mod.execute(context={}, args={"image": "alpine", "command": "echo hi"})
        assert "error" in result
        assert result.get("error_type") == "dependency_not_available"


# ===========================================================================
# Directory structure tests
# ===========================================================================

class TestDirectoryStructure:
    """Validate core_pack directory layout."""

    def test_directory_structure_exists(self) -> None:
        """share/capability_handlers/docker_run/ must exist."""
        assert _HANDLER_DIR.is_dir(), (
            f"Expected directory: {_HANDLER_DIR}"
        )
        assert _ECOSYSTEM_JSON.is_file(), (
            f"Expected file: {_ECOSYSTEM_JSON}"
        )
        assert _HANDLER_JSON.is_file(), (
            f"Expected file: {_HANDLER_JSON}"
        )
        assert _HANDLER_PY.is_file(), (
            f"Expected file: {_HANDLER_PY}"
        )
