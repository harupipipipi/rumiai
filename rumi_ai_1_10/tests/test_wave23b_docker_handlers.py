"""
W23-B Tests — docker_exec / docker_stop / docker_logs / docker_list handlers.

Minimum 15 test cases covering:
  - File existence (handler.json and handler.py for each new handler)
  - Valid JSON and correct fields in each handler.json
  - handler.py contains execute function
  - DockerCapabilityHandler unavailable → error response
  - Existing docker_run/handler.json output_schema has required
  - ecosystem.json has all 5 handlers
"""
from __future__ import annotations

import importlib.util
import json
import sys
import uuid
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent
_CAP_BASE = (
    _ROOT
    / "core_runtime"
    / "core_pack"
    / "core_docker_capability"
    / "share"
    / "capability_handlers"
)
_ECO = (
    _ROOT
    / "core_runtime"
    / "core_pack"
    / "core_docker_capability"
    / "ecosystem.json"
)

_NEW_HANDLERS = ["docker_exec", "docker_stop", "docker_logs", "docker_list"]


# ===========================================================================
# Helper: load a handler.py module dynamically
# ===========================================================================
def _load_handler_module(handler_name: str):
    """Load handler.py as a module without needing the package on sys.path."""
    py_path = _CAP_BASE / handler_name / "handler.py"
    # Use a unique module name each time to avoid caching issues.
    unique_name = f"handler_{handler_name}_{uuid.uuid4().hex[:8]}"
    spec = importlib.util.spec_from_file_location(unique_name, str(py_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ===========================================================================
# 1-4: handler.json existence
# ===========================================================================
@pytest.mark.parametrize("handler_name", _NEW_HANDLERS)
def test_handler_json_exists(handler_name: str):
    p = _CAP_BASE / handler_name / "handler.json"
    assert p.is_file(), f"{p} does not exist"


# ===========================================================================
# 5-8: handler.py existence
# ===========================================================================
@pytest.mark.parametrize("handler_name", _NEW_HANDLERS)
def test_handler_py_exists(handler_name: str):
    p = _CAP_BASE / handler_name / "handler.py"
    assert p.is_file(), f"{p} does not exist"


# ===========================================================================
# 9: handler.json is valid JSON (×4)
# ===========================================================================
@pytest.mark.parametrize("handler_name", _NEW_HANDLERS)
def test_handler_json_valid(handler_name: str):
    p = _CAP_BASE / handler_name / "handler.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert isinstance(data, dict)


# ===========================================================================
# 10: permission_id is correct (×4)
# ===========================================================================
_PERMISSION_MAP = {
    "docker_exec": "docker.exec",
    "docker_stop": "docker.stop",
    "docker_logs": "docker.logs",
    "docker_list": "docker.list",
}


@pytest.mark.parametrize(
    "handler_name,expected_pid",
    list(_PERMISSION_MAP.items()),
)
def test_handler_permission_id(handler_name: str, expected_pid: str):
    p = _CAP_BASE / handler_name / "handler.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["permission_id"] == expected_pid


# ===========================================================================
# 11: handler_id starts with "core." (×4)
# ===========================================================================
@pytest.mark.parametrize("handler_name", _NEW_HANDLERS)
def test_handler_id_prefix(handler_name: str):
    p = _CAP_BASE / handler_name / "handler.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["handler_id"].startswith("core."), (
        f"handler_id {data['handler_id']} does not start with 'core.'"
    )


# ===========================================================================
# 12: input_schema required is correct for handlers that need it (×3)
# ===========================================================================
_INPUT_REQUIRED = {
    "docker_exec": ["container_name", "command"],
    "docker_stop": ["container_name"],
    "docker_logs": ["container_name"],
}


@pytest.mark.parametrize(
    "handler_name,expected_required",
    list(_INPUT_REQUIRED.items()),
)
def test_handler_input_schema_required(
    handler_name: str, expected_required: list
):
    p = _CAP_BASE / handler_name / "handler.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    actual = sorted(data["input_schema"]["required"])
    assert actual == sorted(expected_required)


# ===========================================================================
# 13: docker_list input_schema has no required (or empty)
# ===========================================================================
def test_docker_list_input_schema_no_required():
    p = _CAP_BASE / "docker_list" / "handler.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    req = data["input_schema"].get("required", [])
    assert req == [] or req is None or "required" not in data["input_schema"]


# ===========================================================================
# 14: output_schema has required field (×4)
# ===========================================================================
@pytest.mark.parametrize("handler_name", _NEW_HANDLERS)
def test_handler_output_schema_required(handler_name: str):
    p = _CAP_BASE / handler_name / "handler.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert "required" in data["output_schema"], (
        f"{handler_name} output_schema missing 'required'"
    )
    assert isinstance(data["output_schema"]["required"], list)
    assert len(data["output_schema"]["required"]) > 0


# ===========================================================================
# 15: handler.py has execute function (×4)
# ===========================================================================
@pytest.mark.parametrize("handler_name", _NEW_HANDLERS)
def test_handler_py_has_execute(handler_name: str):
    mod = _load_handler_module(handler_name)
    assert hasattr(mod, "execute"), f"{handler_name}/handler.py has no execute"
    assert callable(mod.execute)


# ===========================================================================
# 16: execute returns error when DockerCapabilityHandler unavailable (×4)
#
# The real DockerCapabilityHandler may be importable in this repo but does
# not yet have handle_exec/stop/logs/list (W23-A pending).  To test the
# "unavailable" fallback path, we force the module-level attribute to None
# after loading, which simulates the ImportError branch.
# ===========================================================================
@pytest.mark.parametrize("handler_name", _NEW_HANDLERS)
def test_handler_py_error_without_docker_handler(handler_name: str):
    mod = _load_handler_module(handler_name)
    # Force the unavailable path regardless of whether the real import succeeded
    mod.DockerCapabilityHandler = None
    result = mod.execute({}, {})
    assert isinstance(result, dict)
    assert "error" in result
    assert result.get("error_type") == "dependency_not_available"


# ===========================================================================
# 17: docker_run/handler.json output_schema has required (existing fix)
# ===========================================================================
def test_docker_run_output_schema_has_required():
    p = _CAP_BASE / "docker_run" / "handler.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert "required" in data["output_schema"], (
        "docker_run output_schema missing 'required' after W23-B patch"
    )
    expected = sorted(["exit_code", "stdout", "stderr"])
    actual = sorted(data["output_schema"]["required"])
    assert actual == expected


# ===========================================================================
# 18: ecosystem.json has all 5 handlers
# ===========================================================================
def test_ecosystem_has_five_handlers():
    data = json.loads(_ECO.read_text(encoding="utf-8"))
    handlers = data["metadata"]["capability_handlers"]
    assert len(handlers) == 5, f"Expected 5 handlers, got {len(handlers)}"
    for name in ["docker_run", "docker_exec", "docker_stop", "docker_logs", "docker_list"]:
        assert name in handlers, f"{name} missing from ecosystem.json"
