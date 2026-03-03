"""
test_wave25a_function_call_dispatch.py

Tests for W25-A: function.call dispatch + DI vocab_registry injection.
Minimum 20 test cases covering all specified scenarios.
"""
from __future__ import annotations

import time
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch, PropertyMock
import pytest

import sys
from pathlib import Path as _Path
from types import ModuleType

# Ensure the project root is on sys.path
_project_root = str(_Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# ---------------------------------------------------------------------------
# Stub modules that capability_executor imports at module level
# ---------------------------------------------------------------------------
def _ensure_stub(mod_name: str):
    if mod_name not in sys.modules:
        stub = ModuleType(mod_name)
        sys.modules[mod_name] = stub
    return sys.modules[mod_name]

_ensure_stub("core_runtime")
_ensure_stub("core_runtime.capability_handler_registry")
_ensure_stub("core_runtime.capability_trust_store")
_ensure_stub("core_runtime.capability_grant_manager")
_ensure_stub("core_runtime.audit_logger")
_ensure_stub("core_runtime.di_container")
_ensure_stub("core_runtime.paths")

# Provide CORE_PACK_ID_PREFIX
sys.modules["core_runtime.paths"].CORE_PACK_ID_PREFIX = "core_"

# Provide minimal get_container
_mock_container = MagicMock()
sys.modules["core_runtime.di_container"].get_container = lambda: _mock_container

# Provide get_audit_logger
_mock_audit_logger = MagicMock()
sys.modules["core_runtime.audit_logger"].get_audit_logger = lambda: _mock_audit_logger

# ---------------------------------------------------------------------------
# FunctionEntry stub
# ---------------------------------------------------------------------------
@dataclass
class FunctionEntry:
    function_id: str
    pack_id: str
    description: str = ""
    requires: List[str] = field(default_factory=list)
    caller_requires: List[str] = field(default_factory=list)
    host_execution: bool = False
    tags: List[str] = field(default_factory=list)
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    function_dir: Any = None
    main_py_path: Any = None
    manifest: Dict[str, Any] = field(default_factory=dict)

    @property
    def qualified_name(self) -> str:
        return f"{self.pack_id}:{self.function_id}"

# ---------------------------------------------------------------------------
# Import after stubs are in place
# ---------------------------------------------------------------------------
from core_runtime.capability_executor import CapabilityExecutor, CapabilityResponse

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_executor(
    function_registry=None,
    approval_manager=None,
    permission_manager=None,
    docker_handler=None,
) -> CapabilityExecutor:
    ex = CapabilityExecutor()
    ex._initialized = True
    ex._handler_registry = MagicMock()
    ex._handler_registry.is_loaded.return_value = True
    ex._trust_store = MagicMock()
    ex._grant_manager = MagicMock()

    ex._function_registry = function_registry
    ex._approval_manager = approval_manager
    ex._permission_manager = permission_manager

    if docker_handler is not None:
        _mock_container.get_or_none.side_effect = lambda name: (
            docker_handler if name == "docker_capability_handler" else None
        )
    else:
        _mock_container.get_or_none.side_effect = lambda name: None

    return ex


def _make_function_registry(entries: Dict[str, FunctionEntry] = None):
    reg = MagicMock()
    _entries = entries or {}
    reg.get.side_effect = lambda qn: _entries.get(qn)
    return reg


def _make_approval_manager(approved_packs: set = None):
    am = MagicMock()
    _approved = approved_packs or set()
    am.is_pack_approved_and_verified.side_effect = lambda pid: (
        (True, None) if pid in _approved else (False, "not_approved")
    )
    return am


def _make_permission_manager(
    mode: str = "permissive",
    has_caller_requires: bool = False,
    caller_requires_result: bool = True,
):
    pm = MagicMock()
    if mode == "permissive":
        pm.has_permission.return_value = True
    else:
        pm.has_permission.return_value = False

    if has_caller_requires:
        pm.check_caller_requires = MagicMock(return_value=caller_requires_result)
    else:
        if hasattr(pm, "check_caller_requires"):
            del pm.check_caller_requires
    return pm


def _core_docker_entry(function_id="run", **kw):
    return FunctionEntry(
        function_id=function_id,
        pack_id="core_docker_capability",
        manifest=kw.get("manifest", {}),
        requires=kw.get("requires", []),
        caller_requires=kw.get("caller_requires", []),
        host_execution=kw.get("host_execution", False),
    )


def _user_entry(pack_id="my_pack", function_id="process", **kw):
    return FunctionEntry(
        function_id=function_id,
        pack_id=pack_id,
        requires=kw.get("requires", []),
        caller_requires=kw.get("caller_requires", []),
        host_execution=kw.get("host_execution", False),
        manifest=kw.get("manifest", {}),
    )


# ===========================================================================
# 1. function.call routing
# ===========================================================================
class TestFunctionCallRouting:

    def test_function_call_routed_to_handler(self):
        """type=function.call dispatches to _execute_function_call."""
        entry = _core_docker_entry()
        reg = _make_function_registry({"core_docker_capability:run": entry})
        am = _make_approval_manager({"core_docker_capability"})
        pm = _make_permission_manager("permissive")
        docker = MagicMock()
        docker.handle_run.return_value = {"status": "ok"}
        ex = _make_executor(reg, am, pm, docker)
        resp = ex.execute("test_principal", {
            "type": "function.call",
            "qualified_name": "core_docker_capability:run",
            "args": {"image": "python:3.12"},
        })
        assert resp.success is True
        assert resp.output == {"status": "ok"}

    def test_normal_capability_unaffected(self):
        """Non function.call requests use normal permission_id flow."""
        ex = _make_executor()
        ex._handler_registry.get_by_permission_id.return_value = None
        resp = ex.execute("p", {"permission_id": "some.perm", "args": {}})
        assert resp.success is False
        assert resp.error_type == "handler_not_found"


# ===========================================================================
# 2. Invalid request
# ===========================================================================
class TestInvalidRequest:

    def test_missing_qualified_name(self):
        ex = _make_executor()
        resp = ex.execute("p", {"type": "function.call"})
        assert resp.error_type == "invalid_request"

    def test_empty_qualified_name(self):
        ex = _make_executor()
        resp = ex.execute("p", {"type": "function.call", "qualified_name": ""})
        assert resp.error_type == "invalid_request"

    def test_non_string_qualified_name(self):
        ex = _make_executor()
        resp = ex.execute("p", {"type": "function.call", "qualified_name": 42})
        assert resp.error_type == "invalid_request"


# ===========================================================================
# 3. Function not found
# ===========================================================================
class TestFunctionNotFound:

    def test_function_not_in_registry(self):
        reg = _make_function_registry({})
        ex = _make_executor(function_registry=reg)
        resp = ex.execute("p", {
            "type": "function.call",
            "qualified_name": "nope:nope",
        })
        assert resp.error_type == "function_not_found"


# ===========================================================================
# 4. Pack not approved
# ===========================================================================
class TestPackNotApproved:

    def test_pack_not_approved(self):
        entry = _user_entry()
        reg = _make_function_registry({"my_pack:process": entry})
        am = _make_approval_manager(set())
        pm = _make_permission_manager("permissive")
        ex = _make_executor(reg, am, pm)
        resp = ex.execute("p", {
            "type": "function.call",
            "qualified_name": "my_pack:process",
        })
        assert resp.error_type == "pack_not_approved"


# ===========================================================================
# 5. Requires denied (non-core)
# ===========================================================================
class TestRequiresDenied:

    def test_requires_denied(self):
        entry = _user_entry(requires=["network"])
        reg = _make_function_registry({"my_pack:process": entry})
        am = _make_approval_manager({"my_pack"})
        pm = MagicMock()
        def _hp(cid, perm):
            if perm == "function.call":
                return True
            return False
        pm.has_permission.side_effect = _hp
        ex = _make_executor(reg, am, pm)
        resp = ex.execute("p", {
            "type": "function.call",
            "qualified_name": "my_pack:process",
        })
        assert resp.error_type == "requires_denied"


# ===========================================================================
# 6. Core pack skips requires
# ===========================================================================
class TestCorePackSkipsRequires:

    def test_core_requires_skipped(self):
        entry = _core_docker_entry(requires=["dangerous"])
        reg = _make_function_registry({"core_docker_capability:run": entry})
        am = _make_approval_manager({"core_docker_capability"})
        pm = _make_permission_manager("permissive")
        docker = MagicMock()
        docker.handle_run.return_value = {"ok": True}
        ex = _make_executor(reg, am, pm, docker)
        resp = ex.execute("p", {
            "type": "function.call",
            "qualified_name": "core_docker_capability:run",
            "args": {},
        })
        assert resp.success is True


# ===========================================================================
# 7. function.call permission denied
# ===========================================================================
class TestPermissionDenied:

    def test_permission_denied(self):
        entry = _core_docker_entry()
        reg = _make_function_registry({"core_docker_capability:run": entry})
        am = _make_approval_manager({"core_docker_capability"})
        pm = MagicMock()
        pm.has_permission.return_value = False
        ex = _make_executor(reg, am, pm)
        resp = ex.execute("p", {
            "type": "function.call",
            "qualified_name": "core_docker_capability:run",
        })
        assert resp.error_type == "permission_denied"


# ===========================================================================
# 8. caller_requires
# ===========================================================================
class TestCallerRequires:

    def test_caller_requires_denied(self):
        entry = _core_docker_entry(caller_requires=["admin"])
        reg = _make_function_registry({"core_docker_capability:run": entry})
        am = _make_approval_manager({"core_docker_capability"})
        pm = _make_permission_manager("permissive", has_caller_requires=True,
                                      caller_requires_result=False)
        ex = _make_executor(reg, am, pm)
        resp = ex.execute("p", {
            "type": "function.call",
            "qualified_name": "core_docker_capability:run",
        })
        assert resp.error_type == "caller_requires_denied"

    def test_caller_requires_fallback_no_method(self):
        """No check_caller_requires + non-empty list -> denied."""
        entry = _core_docker_entry(caller_requires=["admin"])
        reg = _make_function_registry({"core_docker_capability:run": entry})
        am = _make_approval_manager({"core_docker_capability"})
        pm = _make_permission_manager("permissive", has_caller_requires=False)
        ex = _make_executor(reg, am, pm)
        resp = ex.execute("p", {
            "type": "function.call",
            "qualified_name": "core_docker_capability:run",
        })
        assert resp.error_type == "caller_requires_denied"

    def test_empty_caller_requires_passes(self):
        entry = _core_docker_entry(caller_requires=[])
        reg = _make_function_registry({"core_docker_capability:run": entry})
        am = _make_approval_manager({"core_docker_capability"})
        pm = _make_permission_manager("permissive", has_caller_requires=False)
        docker = MagicMock()
        docker.handle_run.return_value = {"ok": True}
        ex = _make_executor(reg, am, pm, docker)
        resp = ex.execute("p", {
            "type": "function.call",
            "qualified_name": "core_docker_capability:run",
            "args": {},
        })
        assert resp.success is True

    def test_caller_requires_success(self):
        entry = _core_docker_entry(caller_requires=["admin"])
        reg = _make_function_registry({"core_docker_capability:run": entry})
        am = _make_approval_manager({"core_docker_capability"})
        pm = _make_permission_manager("permissive", has_caller_requires=True,
                                      caller_requires_result=True)
        docker = MagicMock()
        docker.handle_run.return_value = {"ok": True}
        ex = _make_executor(reg, am, pm, docker)
        resp = ex.execute("p", {
            "type": "function.call",
            "qualified_name": "core_docker_capability:run",
            "args": {},
        })
        assert resp.success is True


# ===========================================================================
# 9. Core docker execution
# ===========================================================================
class TestCoreDockerExecution:

    def test_docker_exec(self):
        entry = _core_docker_entry("exec")
        reg = _make_function_registry({"core_docker_capability:exec": entry})
        am = _make_approval_manager({"core_docker_capability"})
        pm = _make_permission_manager("permissive")
        docker = MagicMock()
        docker.handle_exec.return_value = {"output": "hello"}
        ex = _make_executor(reg, am, pm, docker)
        resp = ex.execute("p", {
            "type": "function.call",
            "qualified_name": "core_docker_capability:exec",
            "args": {"container_id": "abc"},
        })
        assert resp.success is True
        assert resp.output == {"output": "hello"}

    def test_grant_config_from_manifest(self):
        gc = {"max_containers": 5}
        entry = _core_docker_entry("run", manifest={"grant_config": gc})
        reg = _make_function_registry({"core_docker_capability:run": entry})
        am = _make_approval_manager({"core_docker_capability"})
        pm = _make_permission_manager("permissive")
        docker = MagicMock()
        docker.handle_run.return_value = {"id": "123"}
        ex = _make_executor(reg, am, pm, docker)
        resp = ex.execute("p", {
            "type": "function.call",
            "qualified_name": "core_docker_capability:run",
            "args": {"image": "alpine"},
        })
        assert resp.success is True
        _, kwargs = docker.handle_run.call_args
        assert kwargs["grant_config"] == gc


# ===========================================================================
# 10. Unknown core function
# ===========================================================================
class TestUnknownCoreFunction:

    def test_unknown_core_pack(self):
        entry = FunctionEntry(function_id="x", pack_id="core_unknown_thing")
        reg = _make_function_registry({"core_unknown_thing:x": entry})
        am = _make_approval_manager({"core_unknown_thing"})
        pm = _make_permission_manager("permissive")
        ex = _make_executor(reg, am, pm)
        resp = ex.execute("p", {
            "type": "function.call",
            "qualified_name": "core_unknown_thing:x",
        })
        assert resp.error_type == "unknown_core_function"


# ===========================================================================
# 11. User function not_implemented
# ===========================================================================
class TestUserFunction:

    def test_not_implemented(self):
        entry = _user_entry()
        reg = _make_function_registry({"my_pack:process": entry})
        am = _make_approval_manager({"my_pack"})
        pm = _make_permission_manager("permissive")
        ex = _make_executor(reg, am, pm)
        resp = ex.execute("p", {
            "type": "function.call",
            "qualified_name": "my_pack:process",
        })
        assert resp.error_type == "not_implemented"


# ===========================================================================
# 12. host_execution not_implemented
# ===========================================================================
class TestHostExecution:

    def test_not_implemented(self):
        entry = _user_entry(host_execution=True)
        reg = _make_function_registry({"my_pack:process": entry})
        am = _make_approval_manager({"my_pack"})
        pm = _make_permission_manager("permissive")
        ex = _make_executor(reg, am, pm)
        resp = ex.execute("p", {
            "type": "function.call",
            "qualified_name": "my_pack:process",
        })
        assert resp.error_type == "not_implemented"


# ===========================================================================
# 13. Handler exception
# ===========================================================================
class TestHandlerException:

    def test_exception(self):
        entry = _core_docker_entry("run")
        reg = _make_function_registry({"core_docker_capability:run": entry})
        am = _make_approval_manager({"core_docker_capability"})
        pm = _make_permission_manager("permissive")
        docker = MagicMock()
        docker.handle_run.side_effect = RuntimeError("boom")
        ex = _make_executor(reg, am, pm, docker)
        resp = ex.execute("p", {
            "type": "function.call",
            "qualified_name": "core_docker_capability:run",
            "args": {},
        })
        assert resp.error_type == "function_execution_error"
        assert "boom" in resp.error


# ===========================================================================
# 14. latency_ms
# ===========================================================================
class TestLatency:

    def test_latency_populated(self):
        entry = _core_docker_entry()
        reg = _make_function_registry({"core_docker_capability:run": entry})
        am = _make_approval_manager({"core_docker_capability"})
        pm = _make_permission_manager("permissive")
        docker = MagicMock()
        docker.handle_run.return_value = {}
        ex = _make_executor(reg, am, pm, docker)
        resp = ex.execute("p", {
            "type": "function.call",
            "qualified_name": "core_docker_capability:run",
            "args": {},
        })
        assert resp.latency_ms >= 0


# ===========================================================================
# 15. Audit log
# ===========================================================================
class TestAuditLog:

    def test_audit_called(self):
        entry = _core_docker_entry()
        reg = _make_function_registry({"core_docker_capability:run": entry})
        am = _make_approval_manager({"core_docker_capability"})
        pm = _make_permission_manager("permissive")
        docker = MagicMock()
        docker.handle_run.return_value = {"ok": True}
        ex = _make_executor(reg, am, pm, docker)
        ex._audit = MagicMock()
        resp = ex.execute("p", {
            "type": "function.call",
            "qualified_name": "core_docker_capability:run",
            "args": {},
        })
        assert resp.success is True
        assert ex._audit.called


# ===========================================================================
# 16. DI vocab_registry injection
# ===========================================================================
class TestDIVocabRegistry:

    def test_vocab_registry_injected(self):
        import pathlib
        di_src = pathlib.Path("core_runtime/di_container.py").read_text()
        assert 'get_or_none("vocab_registry")' in di_src
        assert "FunctionRegistry(vocab_registry=" in di_src


# ===========================================================================
# 17. function_registry unavailable
# ===========================================================================
class TestRegistryUnavailable:

    def test_unavailable(self):
        ex = _make_executor(function_registry=None)
        resp = ex.execute("p", {
            "type": "function.call",
            "qualified_name": "some:fn",
        })
        assert resp.error_type == "function_registry_unavailable"


# ===========================================================================
# 18. Docker handler error result
# ===========================================================================
class TestDockerErrorResult:

    def test_error_in_result(self):
        entry = _core_docker_entry("run")
        reg = _make_function_registry({"core_docker_capability:run": entry})
        am = _make_approval_manager({"core_docker_capability"})
        pm = _make_permission_manager("permissive")
        docker = MagicMock()
        docker.handle_run.return_value = {"error": "container failed"}
        ex = _make_executor(reg, am, pm, docker)
        resp = ex.execute("p", {
            "type": "function.call",
            "qualified_name": "core_docker_capability:run",
            "args": {},
        })
        assert resp.success is False
        assert "container failed" in resp.error


# ===========================================================================
# 19. Docker handler unavailable
# ===========================================================================
class TestDockerHandlerUnavailable:

    def test_handler_none(self):
        entry = _core_docker_entry("run")
        reg = _make_function_registry({"core_docker_capability:run": entry})
        am = _make_approval_manager({"core_docker_capability"})
        pm = _make_permission_manager("permissive")
        ex = _make_executor(reg, am, pm, docker_handler=None)
        resp = ex.execute("p", {
            "type": "function.call",
            "qualified_name": "core_docker_capability:run",
            "args": {},
        })
        assert resp.success is False
        assert resp.error_type == "initialization_error"


# ===========================================================================
# 20. Multiple functions from same core pack
# ===========================================================================
class TestMultipleFunctions:

    def test_stop_function(self):
        entry = _core_docker_entry("stop")
        reg = _make_function_registry({"core_docker_capability:stop": entry})
        am = _make_approval_manager({"core_docker_capability"})
        pm = _make_permission_manager("permissive")
        docker = MagicMock()
        docker.handle_stop.return_value = {"stopped": True}
        ex = _make_executor(reg, am, pm, docker)
        resp = ex.execute("p", {
            "type": "function.call",
            "qualified_name": "core_docker_capability:stop",
            "args": {"container_id": "abc"},
        })
        assert resp.success is True
        docker.handle_stop.assert_called_once()
