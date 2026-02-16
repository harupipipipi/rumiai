"""
test_unit_executor_security.py - P0 セキュリティ改善のテスト

テスト対象:
  - kind ホワイトリスト (I-02)
  - TOCTOU 緩和 (I-03)
  - setuid/setgid チェック (I-06)
"""

from __future__ import annotations

import hashlib
import os
import shutil
import stat as stat_module
import tempfile
import time
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Stub dataclasses — avoid importing real modules with heavy side effects
# ---------------------------------------------------------------------------

@dataclass
class _StubUnitMeta:
    unit_id: str = "test_unit"
    version: str = "1.0.0"
    kind: str = "python"
    entrypoint: Optional[str] = "handler.py"
    declared_by_pack_id: str = "test_pack"
    declared_at: str = ""
    requires_individual_approval: bool = True
    exec_modes_allowed: List[str] = field(
        default_factory=lambda: ["host_capability"],
    )
    permission_id: str = "perm.test"
    unit_dir: Optional[Path] = None
    store_id: str = "default"
    namespace: str = "ns"
    name: str = "test"


@dataclass
class _StubTrustResult:
    trusted: bool = True
    reason: str = ""


@dataclass
class _StubGrantResult:
    allowed: bool = True
    reason: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_UNIT_REF = {"store_id": "s1", "unit_id": "test_unit", "version": "1.0.0"}
_PRINCIPAL = "pack_a"

# Patch targets — local imports inside execute() resolve from origin modules
_P_APPROVAL = "rumi_ai_1_10.core_runtime.approval_manager.get_approval_manager"
_P_STORE_REG = "rumi_ai_1_10.core_runtime.store_registry.get_store_registry"
_P_UNIT_REG = "rumi_ai_1_10.core_runtime.unit_registry.get_unit_registry"
_P_UNIT_REF_CLS = "rumi_ai_1_10.core_runtime.unit_registry.UnitRef"
_P_GRANT = (
    "rumi_ai_1_10.core_runtime.capability_grant_manager"
    ".get_capability_grant_manager"
)
_P_TRUST = "rumi_ai_1_10.core_runtime.unit_trust_store.get_unit_trust_store"
_P_AUDIT = "rumi_ai_1_10.core_runtime.audit_logger.get_audit_logger"
_P_PLATFORM = "rumi_ai_1_10.core_runtime.unit_executor.platform.system"


def _build_gate_patches(
    unit_meta: Optional[_StubUnitMeta] = None,
    trust_sha: str = "abcd1234",
    trust_ok: bool = True,
    grant_ok: bool = True,
):
    """Create context-manager patches that stub gates 1-5."""

    if unit_meta is None:
        unit_meta = _StubUnitMeta(
            unit_dir=Path("/tmp/fake_store/ns/test/1.0.0"),
        )

    store_def = MagicMock()
    store_def.root_path = "/tmp/fake_store"

    am = MagicMock()
    am.is_pack_approved_and_verified.return_value = (True, "ok")

    sr = MagicMock()
    sr.get_store.return_value = store_def

    ur = MagicMock()
    ur.get_unit_by_ref.return_value = unit_meta
    ur.compute_entrypoint_sha256.return_value = trust_sha

    gm = MagicMock()
    gm.check.return_value = _StubGrantResult(allowed=grant_ok, reason="ok")

    ts = MagicMock()
    ts.is_loaded.return_value = True
    ts.is_trusted.return_value = _StubTrustResult(
        trusted=trust_ok, reason="ok",
    )

    return {
        "approval": patch(_P_APPROVAL, return_value=am),
        "store_reg": patch(_P_STORE_REG, return_value=sr),
        "unit_reg": patch(_P_UNIT_REG, return_value=ur),
        "unit_ref_cls": patch(_P_UNIT_REF_CLS),
        "grant": patch(_P_GRANT, return_value=gm),
        "trust": patch(_P_TRUST, return_value=ts),
        "audit": patch(_P_AUDIT, return_value=MagicMock()),
    }


def _enter(patches: dict):
    for p in patches.values():
        p.start()


def _exit(patches: dict):
    for p in patches.values():
        p.stop()


def _make_executor():
    from rumi_ai_1_10.core_runtime.unit_executor import UnitExecutor
    return UnitExecutor()


# ========================================================================
# Test: kind whitelist (I-02)
# ========================================================================

class TestKindWhitelist(unittest.TestCase):
    """Gate 4.5: unknown kind -> reject with error_type='unknown_kind'."""

    def test_allowed_kinds_constant(self):
        from rumi_ai_1_10.core_runtime.unit_executor import ALLOWED_KINDS
        self.assertEqual(ALLOWED_KINDS, frozenset({"data", "python", "binary"}))

    def test_unknown_kind_wasm_rejected(self):
        meta = _StubUnitMeta(
            kind="wasm",
            unit_dir=Path("/tmp/fake_store/ns/test/1.0.0"),
        )
        patches = _build_gate_patches(unit_meta=meta)
        _enter(patches)
        try:
            result = _make_executor().execute(
                _PRINCIPAL, _UNIT_REF, "host_capability", {},
            )
            self.assertFalse(result.success)
            self.assertEqual(result.error_type, "unknown_kind")
            self.assertIn("wasm", result.error)
        finally:
            _exit(patches)

    def test_unknown_kind_native_rejected(self):
        meta = _StubUnitMeta(
            kind="native",
            unit_dir=Path("/tmp/fake_store/ns/test/1.0.0"),
        )
        patches = _build_gate_patches(unit_meta=meta)
        _enter(patches)
        try:
            result = _make_executor().execute(
                _PRINCIPAL, _UNIT_REF, "host_capability", {},
            )
            self.assertFalse(result.success)
            self.assertEqual(result.error_type, "unknown_kind")
        finally:
            _exit(patches)

    def test_data_kind_passes_whitelist_but_unsupported(self):
        """data passes kind gate but host_capability rejects it."""
        meta = _StubUnitMeta(
            kind="data",
            entrypoint=None,
            unit_dir=Path("/tmp/fake_store/ns/test/1.0.0"),
        )
        patches = _build_gate_patches(unit_meta=meta)
        _enter(patches)
        try:
            result = _make_executor().execute(
                _PRINCIPAL, _UNIT_REF, "host_capability", {},
            )
            self.assertFalse(result.success)
            self.assertEqual(result.error_type, "unsupported_kind")
        finally:
            _exit(patches)


# ========================================================================
# Test: TOCTOU mitigation (I-03)
# ========================================================================

class TestTOCTOUMitigation(unittest.TestCase):
    """Entrypoint is read into memory, re-verified, written to temp file."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._ep_content = b'def execute(args): return {"ok": True}\n'
        self._ep_sha = hashlib.sha256(self._ep_content).hexdigest()

        ep_dir = Path(self._tmpdir) / "ns" / "test" / "1.0.0"
        ep_dir.mkdir(parents=True)
        (ep_dir / "handler.py").write_bytes(self._ep_content)

        self._ep_dir = ep_dir

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_toctou_mismatch_detected(self):
        """If trust hash != re-read hash, reject with toctou_mismatch."""
        meta = _StubUnitMeta(
            kind="python",
            unit_dir=self._ep_dir,
            entrypoint="handler.py",
        )
        wrong_sha = hashlib.sha256(b"TAMPERED").hexdigest()
        patches = _build_gate_patches(unit_meta=meta, trust_sha=wrong_sha)
        _enter(patches)
        try:
            result = _make_executor().execute(
                _PRINCIPAL, _UNIT_REF, "host_capability", {},
            )
            self.assertFalse(result.success)
            self.assertEqual(result.error_type, "toctou_mismatch")
        finally:
            _exit(patches)

    def test_toctou_read_error(self):
        """If entrypoint disappears after trust check, toctou_read_error."""
        meta = _StubUnitMeta(
            kind="python",
            unit_dir=self._ep_dir,
            entrypoint="handler.py",
        )
        patches = _build_gate_patches(
            unit_meta=meta, trust_sha=self._ep_sha,
        )
        _enter(patches)
        try:
            # Remove file to trigger read error
            (self._ep_dir / "handler.py").unlink()
            result = _make_executor().execute(
                _PRINCIPAL, _UNIT_REF, "host_capability", {},
            )
            self.assertFalse(result.success)
            self.assertEqual(result.error_type, "toctou_read_error")
        finally:
            _exit(patches)

    def test_verified_content_forwarded(self):
        """execute() passes verified_content to _execute_python_host."""
        meta = _StubUnitMeta(
            kind="python",
            unit_dir=self._ep_dir,
            entrypoint="handler.py",
        )
        patches = _build_gate_patches(
            unit_meta=meta, trust_sha=self._ep_sha,
        )
        _enter(patches)
        try:
            executor = _make_executor()
            captured: Dict[str, Any] = {}

            def spy(um, args, timeout, start, vc=None):
                captured["verified_content"] = vc
                from rumi_ai_1_10.core_runtime.unit_executor import (
                    UnitExecutionResult,
                )
                return UnitExecutionResult(
                    success=True, execution_mode="host_capability",
                )

            executor._execute_python_host = spy  # type: ignore[assignment]
            result = executor.execute(
                _PRINCIPAL, _UNIT_REF, "host_capability", {},
            )
            self.assertTrue(result.success)
            self.assertEqual(captured["verified_content"], self._ep_content)
        finally:
            _exit(patches)

    def test_temp_files_cleaned_up(self):
        """All temp files are removed after execution."""
        meta = _StubUnitMeta(
            kind="python",
            unit_dir=self._ep_dir,
            entrypoint="handler.py",
        )
        patches = _build_gate_patches(
            unit_meta=meta, trust_sha=self._ep_sha,
        )
        _enter(patches)
        try:
            created: List[str] = []
            _real_mkstemp = tempfile.mkstemp

            def tracking(*a, **kw):
                fd, path = _real_mkstemp(*a, **kw)
                created.append(path)
                return fd, path

            with patch(
                "rumi_ai_1_10.core_runtime.unit_executor.tempfile.mkstemp",
                side_effect=tracking,
            ), patch(
                "rumi_ai_1_10.core_runtime.unit_executor.subprocess.run",
            ) as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0, stdout='{"ok": true}', stderr="",
                )
                _make_executor().execute(
                    _PRINCIPAL, _UNIT_REF, "host_capability", {},
                )

            for path in created:
                self.assertFalse(
                    os.path.exists(path),
                    f"Temp file not cleaned up: {path}",
                )
        finally:
            _exit(patches)

    # ---- A-18: binary kind TOCTOU tests ----

    def test_binary_toctou_mismatch_detected(self):
        """If trust hash != re-read hash for binary kind, reject with toctou_mismatch."""
        meta = _StubUnitMeta(
            kind="binary",
            unit_dir=self._ep_dir,
            entrypoint="handler.py",
        )
        wrong_sha = hashlib.sha256(b"TAMPERED").hexdigest()
        patches = _build_gate_patches(unit_meta=meta, trust_sha=wrong_sha)
        _enter(patches)
        try:
            result = _make_executor().execute(
                _PRINCIPAL, _UNIT_REF, "host_capability", {},
            )
            self.assertFalse(result.success)
            self.assertEqual(result.error_type, "toctou_mismatch")
        finally:
            _exit(patches)

    def test_binary_toctou_read_error(self):
        """If binary entrypoint disappears after trust check, toctou_read_error."""
        meta = _StubUnitMeta(
            kind="binary",
            unit_dir=self._ep_dir,
            entrypoint="handler.py",
        )
        patches = _build_gate_patches(
            unit_meta=meta, trust_sha=self._ep_sha,
        )
        _enter(patches)
        try:
            # Remove file to trigger read error
            (self._ep_dir / "handler.py").unlink()
            result = _make_executor().execute(
                _PRINCIPAL, _UNIT_REF, "host_capability", {},
            )
            self.assertFalse(result.success)
            self.assertEqual(result.error_type, "toctou_read_error")
        finally:
            _exit(patches)


# ========================================================================
# Test: setuid/setgid check (I-06)
# ========================================================================

class TestSetuidSetgidCheck(unittest.TestCase):
    """Binary entrypoints with setuid/setgid bits must be rejected."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        ep_dir = Path(self._tmpdir) / "ns" / "test" / "1.0.0"
        ep_dir.mkdir(parents=True)
        ep_file = ep_dir / "run.bin"
        ep_file.write_bytes(b"#!/bin/sh\necho ok\n")
        ep_file.chmod(0o755)

        self._ep_dir = ep_dir
        self._ep_file = ep_file
        self._ep_content = b"#!/bin/sh\necho ok\n"
        self._ep_sha = hashlib.sha256(self._ep_content).hexdigest()

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    # -- helpers for os.stat side_effect ----------------------------------

    @staticmethod
    def _stat_with_mode(target_path: str, fake_mode: int):
        """Return a side_effect that fakes st_mode for *target_path* only."""
        _real = os.stat

        def _side(path, *a, **kw):
            real_result = _real(path, *a, **kw)
            if str(path) == target_path:
                fake = MagicMock()
                fake.st_mode = fake_mode
                return fake
            return real_result

        return _side

    # -- tests ------------------------------------------------------------

    @patch(_P_PLATFORM, return_value="Linux")
    def test_setuid_rejected(self, _):
        meta = _StubUnitMeta(
            kind="binary",
            unit_dir=self._ep_dir,
            entrypoint="run.bin",
        )
        patches = _build_gate_patches(
            unit_meta=meta, trust_sha=self._ep_sha,
        )
        _enter(patches)
        try:
            with patch(
                "rumi_ai_1_10.core_runtime.unit_executor.os.stat",
                side_effect=self._stat_with_mode(
                    str(self._ep_file), 0o104755,
                ),
            ):
                result = _make_executor().execute(
                    _PRINCIPAL, _UNIT_REF, "host_capability", {},
                )
            self.assertFalse(result.success)
            self.assertEqual(result.error_type, "security_violation")
            self.assertIn("setuid/setgid", result.error)
        finally:
            _exit(patches)

    @patch(_P_PLATFORM, return_value="Linux")
    def test_setgid_rejected(self, _):
        meta = _StubUnitMeta(
            kind="binary",
            unit_dir=self._ep_dir,
            entrypoint="run.bin",
        )
        patches = _build_gate_patches(
            unit_meta=meta, trust_sha=self._ep_sha,
        )
        _enter(patches)
        try:
            with patch(
                "rumi_ai_1_10.core_runtime.unit_executor.os.stat",
                side_effect=self._stat_with_mode(
                    str(self._ep_file), 0o102755,
                ),
            ):
                result = _make_executor().execute(
                    _PRINCIPAL, _UNIT_REF, "host_capability", {},
                )
            self.assertFalse(result.success)
            self.assertEqual(result.error_type, "security_violation")
        finally:
            _exit(patches)

    @patch(_P_PLATFORM, return_value="Linux")
    def test_normal_perms_pass(self, _):
        meta = _StubUnitMeta(
            kind="binary",
            unit_dir=self._ep_dir,
            entrypoint="run.bin",
        )
        patches = _build_gate_patches(
            unit_meta=meta, trust_sha=self._ep_sha,
        )
        _enter(patches)
        try:
            with patch(
                "rumi_ai_1_10.core_runtime.unit_executor.os.stat",
                side_effect=self._stat_with_mode(
                    str(self._ep_file), 0o100755,
                ),
            ), patch(
                "rumi_ai_1_10.core_runtime.unit_executor.subprocess.run",
            ) as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0, stdout='{"ok": true}', stderr="",
                )
                result = _make_executor().execute(
                    _PRINCIPAL, _UNIT_REF, "host_capability", {},
                )
            self.assertNotEqual(result.error_type, "security_violation")
        finally:
            _exit(patches)

    @patch(_P_PLATFORM, return_value="Windows")
    def test_windows_skips_check(self, _):
        meta = _StubUnitMeta(
            kind="binary",
            unit_dir=self._ep_dir,
            entrypoint="run.bin",
        )
        patches = _build_gate_patches(
            unit_meta=meta, trust_sha=self._ep_sha,
        )
        _enter(patches)
        try:
            with patch(
                "rumi_ai_1_10.core_runtime.unit_executor.subprocess.run",
            ) as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0, stdout='{"ok": true}', stderr="",
                )
                result = _make_executor().execute(
                    _PRINCIPAL, _UNIT_REF, "host_capability", {},
                )
            self.assertNotEqual(result.error_type, "security_violation")
        finally:
            _exit(patches)

    # ---- A-18: os.stat() failure test ----

    @patch(_P_PLATFORM, return_value="Linux")
    def test_stat_oserror_returns_internal_error(self, _):
        """os.stat() raising OSError should yield internal_error."""
        meta = _StubUnitMeta(
            kind="binary",
            unit_dir=self._ep_dir,
            entrypoint="run.bin",
        )
        patches = _build_gate_patches(
            unit_meta=meta, trust_sha=self._ep_sha,
        )
        _enter(patches)
        try:
            with patch(
                "rumi_ai_1_10.core_runtime.unit_executor.os.stat",
                side_effect=OSError("Permission denied"),
            ):
                result = _make_executor().execute(
                    _PRINCIPAL, _UNIT_REF, "host_capability", {},
                )
            self.assertFalse(result.success)
            self.assertEqual(result.error_type, "internal_error")
        finally:
            _exit(patches)


if __name__ == "__main__":
    unittest.main()
