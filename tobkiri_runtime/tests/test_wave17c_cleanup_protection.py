"""Tests for Wave 17-C: Cleanup, env protection, IR protected keys."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from threading import RLock
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Ensure core_runtime is importable
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# ---------------------------------------------------------------------------
# Helpers — lightweight fakes so we don't need the full runtime
# ---------------------------------------------------------------------------


class _FakeIR:
    """Minimal InterfaceRegistry stand-in for lifecycle handler tests."""

    def __init__(self):
        self._store: Dict[str, list] = {}
        self._lock = RLock()

    def register(self, key, value, meta=None):
        self._store.setdefault(key, []).append({
            "key": key,
            "value": value,
            "meta": meta or {},
            "ts": "2025-01-01T00:00:00Z",
        })

    def list(self, prefix=None, include_meta=False):
        out = {}
        for k, items in self._store.items():
            if prefix and not k.startswith(prefix):
                continue
            if include_meta:
                last = items[-1] if items else None
                out[k] = {
                    "count": len(items),
                    "last_ts": last.get("ts") if last else None,
                    "last_meta": last.get("meta") if last else None,
                }
            else:
                out[k] = len(items)
        return out

    def unregister(self, key, predicate=None):
        if key not in self._store:
            return 0
        if predicate is None:
            count = len(self._store[key])
            del self._store[key]
            return count
        kept, removed = [], 0
        for entry in self._store[key]:
            if predicate(entry):
                removed += 1
            else:
                kept.append(entry)
        if kept:
            self._store[key] = kept
        else:
            del self._store[key]
        return removed


class _FakeKernel:
    def __init__(self, ir):
        self.interface_registry = ir


def _make_handler(ir=None):
    """Return a minimal Mixin instance wired to the fake IR."""
    from core_runtime.api.pack_lifecycle_handlers import PackLifecycleHandlersMixin

    class Handler(PackLifecycleHandlersMixin):
        pass

    h = Handler()
    h.container_orchestrator = None
    h.approval_manager = None
    h.host_privilege_manager = None
    if ir is not None:
        h.kernel = _FakeKernel(ir)
    else:
        h.kernel = None
    return h


# ===================================================================
# 1. IR cleanup on uninstall
# ===================================================================


class TestUninstallIRCleanup:
    """_uninstall_pack should remove IR entries owned by the uninstalled pack."""

    def test_ir_entries_removed_on_uninstall(self):
        ir = _FakeIR()
        ir.register("tool.search", "v1", meta={"owner_pack": "pack_a"})
        ir.register("tool.calc", "v2", meta={"owner_pack": "pack_b"})
        ir.register("tool.web", "v3", meta={"pack_id": "pack_a"})

        handler = _make_handler(ir)
        result = handler._uninstall_pack("pack_a")

        assert result["steps"].get("ir_cleanup") is True
        remaining = ir.list()
        assert "tool.search" not in remaining
        assert "tool.calc" in remaining
        assert "tool.web" not in remaining

    def test_ir_cleanup_no_ir_available(self):
        """When no IR is available, step should be None (skipped)."""
        handler = _make_handler(ir=None)
        result = handler._uninstall_pack("pack_x")
        assert result["steps"].get("ir_cleanup") is None

    def test_ir_cleanup_multiple_meta_fields(self):
        """Entries using _source_pack_id / registered_by should also be cleaned."""
        ir = _FakeIR()
        ir.register("hook.a", "v", meta={"_source_pack_id": "pack_c"})
        ir.register("hook.b", "v", meta={"registered_by": "pack_c"})
        ir.register("hook.c", "v", meta={"source": "pack_c"})
        handler = _make_handler(ir)
        result = handler._uninstall_pack("pack_c")
        assert result["steps"]["ir_cleanup"] is True
        assert len(ir.list()) == 0


# ===================================================================
# 2. Network Grant revoke on uninstall
# ===================================================================


class TestUninstallNetworkGrantRevoke:
    def test_network_grant_revoked(self):
        handler = _make_handler()
        mock_ngm = MagicMock()
        with patch(
            "core_runtime.network_grant_manager.get_network_grant_manager",
            return_value=mock_ngm,
        ):
            result = handler._uninstall_pack("pack_net")

        mock_ngm.revoke_network_access.assert_called_once_with(
            "pack_net", reason="Pack pack_net uninstalled"
        )
        assert result["steps"]["network_grant_revoke"] is True

    def test_network_grant_revoke_failure_recorded(self):
        handler = _make_handler()
        mock_ngm = MagicMock()
        mock_ngm.revoke_network_access.side_effect = RuntimeError("boom")
        with patch(
            "core_runtime.network_grant_manager.get_network_grant_manager",
            return_value=mock_ngm,
        ):
            result = handler._uninstall_pack("pack_err")

        assert result["steps"]["network_grant_revoke"] is False
        assert any(e["step"] == "network_grant_revoke" for e in result["errors"])


# ===================================================================
# 3. sys.path shadow detection
# ===================================================================


class TestSysPathShadowDetection:
    def test_shadow_module_blocked(self, tmp_path):
        """A directory containing 'os.py' must NOT be added to sys.path."""
        from core_runtime.component_lifecycle import _has_shadow_module

        evil_dir = tmp_path / "evil_pack"
        evil_dir.mkdir()
        (evil_dir / "os.py").write_text("# shadow os")

        result = _has_shadow_module(evil_dir)
        assert result == "os"

    def test_safe_directory_allowed(self, tmp_path):
        from core_runtime.component_lifecycle import _has_shadow_module

        safe_dir = tmp_path / "safe_pack"
        safe_dir.mkdir()
        (safe_dir / "my_module.py").write_text("# safe")

        result = _has_shadow_module(safe_dir)
        assert result is None

    def test_shadow_package_dir_blocked(self, tmp_path):
        """A sub-directory named 'json' (package) should also be caught."""
        from core_runtime.component_lifecycle import _has_shadow_module

        pack_dir = tmp_path / "bad_pack"
        pack_dir.mkdir()
        (pack_dir / "json").mkdir()
        (pack_dir / "json" / "__init__.py").write_text("")

        result = _has_shadow_module(pack_dir)
        assert result == "json"

    def test_ensure_components_skips_shadow(self, tmp_path):
        """_ensure_components_on_syspath should skip a dir with shadow modules."""
        from core_runtime.component_lifecycle import ComponentLifecycleExecutor

        evil_dir = tmp_path / "shadow_pack"
        evil_dir.mkdir()
        (evil_dir / "subprocess.py").write_text("# evil")

        diag = MagicMock()
        journal = MagicMock()
        executor = ComponentLifecycleExecutor(diagnostics=diag, install_journal=journal)

        comp = MagicMock()
        comp.path = str(evil_dir)

        original_path = list(sys.path)
        executor._ensure_components_on_syspath([comp])

        assert str(evil_dir.resolve()) not in sys.path
        sys.path[:] = original_path


# ===================================================================
# 4. RUMI_SECURITY_MODE freeze / restore
# ===================================================================


class TestEnvVarFreeze:
    def test_security_mode_restored_after_tampering(self):
        from core_runtime.component_lifecycle import ComponentLifecycleExecutor

        os.environ["RUMI_SECURITY_MODE"] = "strict"
        snapshot = ComponentLifecycleExecutor._snapshot_env()
        assert snapshot["RUMI_SECURITY_MODE"] == "strict"

        os.environ["RUMI_SECURITY_MODE"] = "permissive"
        ComponentLifecycleExecutor._restore_env(snapshot)
        assert os.environ.get("RUMI_SECURITY_MODE") == "strict"

        del os.environ["RUMI_SECURITY_MODE"]

    def test_security_mode_deleted_if_was_absent(self):
        from core_runtime.component_lifecycle import ComponentLifecycleExecutor

        os.environ.pop("RUMI_SECURITY_MODE", None)
        snapshot = ComponentLifecycleExecutor._snapshot_env()

        os.environ["RUMI_SECURITY_MODE"] = "permissive"
        ComponentLifecycleExecutor._restore_env(snapshot)
        assert "RUMI_SECURITY_MODE" not in os.environ

    def test_no_change_if_not_tampered(self):
        from core_runtime.component_lifecycle import ComponentLifecycleExecutor

        os.environ["RUMI_SECURITY_MODE"] = "strict"
        snapshot = ComponentLifecycleExecutor._snapshot_env()

        ComponentLifecycleExecutor._restore_env(snapshot)
        assert os.environ.get("RUMI_SECURITY_MODE") == "strict"

        del os.environ["RUMI_SECURITY_MODE"]


# ===================================================================
# 5. IR protected key registration WARNING
# ===================================================================


class TestIRProtectedKeys:
    def _get_ir(self):
        from core_runtime.interface_registry import InterfaceRegistry
        return InterfaceRegistry()

    def test_protected_key_warning_mode(self):
        """In default mode, registration to protected key succeeds."""
        ir = self._get_ir()
        os.environ.pop("RUMI_BLOCK_PROTECTED_KEYS", None)

        ir.register("flow.hooks.before_step", "handler_fn", meta={"_source_pack_id": "test"})
        assert ir.get("flow.hooks.before_step") == "handler_fn"

    def test_protected_key_with_system_flag(self):
        """Registration with _system=True should work without warning."""
        ir = self._get_ir()
        os.environ.pop("RUMI_BLOCK_PROTECTED_KEYS", None)

        ir.register("flow.hooks.before_step", "sys_handler", meta={"_system": True})
        assert ir.get("flow.hooks.before_step") == "sys_handler"

    def test_protected_key_prefix_flow_construct(self):
        """Keys starting with 'flow.construct.' should be protected."""
        ir = self._get_ir()
        os.environ.pop("RUMI_BLOCK_PROTECTED_KEYS", None)

        ir.register("flow.construct.my_flow", "val", meta={"_source_pack_id": "test"})
        assert ir.get("flow.construct.my_flow") == "val"

    def test_protected_key_prefix_kernel(self):
        """Keys starting with 'kernel:' should be protected."""
        ir = self._get_ir()
        os.environ.pop("RUMI_BLOCK_PROTECTED_KEYS", None)

        ir.register("kernel:secret", "val")
        assert ir.get("kernel:secret") == "val"


# ===================================================================
# 6. RUMI_BLOCK_PROTECTED_KEYS=1 blocking
# ===================================================================


class TestIRProtectedKeysBlocking:
    def _get_ir(self):
        from core_runtime.interface_registry import InterfaceRegistry
        return InterfaceRegistry()

    def test_block_mode_raises(self):
        ir = self._get_ir()
        os.environ["RUMI_BLOCK_PROTECTED_KEYS"] = "1"
        try:
            with pytest.raises(PermissionError, match="protected key"):
                ir.register("io.http.server", "evil_server")
            assert ir.get("io.http.server") is None
        finally:
            os.environ.pop("RUMI_BLOCK_PROTECTED_KEYS", None)

    def test_block_mode_allows_system(self):
        ir = self._get_ir()
        os.environ["RUMI_BLOCK_PROTECTED_KEYS"] = "1"
        try:
            ir.register("io.http.server", "sys_server", meta={"_system": True})
            assert ir.get("io.http.server") == "sys_server"
        finally:
            os.environ.pop("RUMI_BLOCK_PROTECTED_KEYS", None)

    def test_block_mode_register_if_absent(self):
        """register_if_absent should also respect block mode."""
        ir = self._get_ir()
        os.environ["RUMI_BLOCK_PROTECTED_KEYS"] = "1"
        try:
            with pytest.raises(PermissionError, match="protected key"):
                ir.register_if_absent("flow.error_handler", "evil")
            assert ir.get("flow.error_handler") is None
        finally:
            os.environ.pop("RUMI_BLOCK_PROTECTED_KEYS", None)

    def test_non_protected_key_unaffected(self):
        """Non-protected keys should work normally in block mode."""
        ir = self._get_ir()
        os.environ["RUMI_BLOCK_PROTECTED_KEYS"] = "1"
        try:
            ir.register("my.custom.key", "value")
            assert ir.get("my.custom.key") == "value"
        finally:
            os.environ.pop("RUMI_BLOCK_PROTECTED_KEYS", None)
