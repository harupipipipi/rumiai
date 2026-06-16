from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from core_runtime.approval_manager import PackStatus
from core_runtime.pack_function_runtime import assert_pack_function_executable


def _make_entry(
    function_dir: Path,
    *,
    pack_id: str = "sample_pack",
    function_id: str = "sample_func",
    entrypoint: str = "main.py:run",
    calling_convention: str = "subprocess",
    grant_config=None,
):
    return SimpleNamespace(
        pack_id=pack_id,
        function_id=function_id,
        qualified_name=f"{pack_id}:{function_id}",
        function_dir=str(function_dir),
        entrypoint=entrypoint,
        calling_convention=calling_convention,
        permission_id=None,
        handler_py_sha256=None,
        grant_config=grant_config,
        manifest={},
        command=[],
        main_binary_path=None,
        is_builtin=False,
    )


def _make_approval_manager(
    *,
    status=PackStatus.APPROVED,
    verify_hash=True,
    is_core=False,
    is_trusted_builtin=False,
):
    manager = MagicMock()
    manager.get_status.return_value = status
    manager.verify_hash.return_value = verify_hash
    manager._is_core_pack.return_value = is_core
    manager._is_trusted_builtin_pack.return_value = is_trusted_builtin
    return manager


def test_unapproved_pack_function_is_rejected(tmp_path, monkeypatch):
    function_dir = tmp_path / "fn"
    function_dir.mkdir()
    (function_dir / "main.py").write_text("def run(context, args): return args\n", encoding="utf-8")
    entry = _make_entry(function_dir)
    monkeypatch.setattr("core_runtime.pack_function_runtime.BASE_DIR", tmp_path)

    monkeypatch.setattr(
        "core_runtime.pack_function_policy.get_approval_manager",
        lambda: _make_approval_manager(status=PackStatus.PENDING),
    )

    with pytest.raises(PermissionError, match="Pack is not approved"):
        assert_pack_function_executable(entry)


def test_modified_pack_function_is_rejected(tmp_path, monkeypatch):
    function_dir = tmp_path / "fn"
    function_dir.mkdir()
    (function_dir / "main.py").write_text("def run(context, args): return args\n", encoding="utf-8")
    entry = _make_entry(function_dir)
    monkeypatch.setattr("core_runtime.pack_function_runtime.BASE_DIR", tmp_path)

    monkeypatch.setattr(
        "core_runtime.pack_function_policy.get_approval_manager",
        lambda: _make_approval_manager(verify_hash=False),
    )

    with pytest.raises(PermissionError, match="Pack hash verification failed"):
        assert_pack_function_executable(entry)


def test_core_builtin_function_is_allowed(tmp_path, monkeypatch):
    function_dir = tmp_path / "fn"
    function_dir.mkdir()
    (function_dir / "main.py").write_text("def run(context, args): return args\n", encoding="utf-8")
    entry = _make_entry(function_dir, pack_id="core_example")
    monkeypatch.setattr("core_runtime.pack_function_runtime.BASE_DIR", tmp_path)

    monkeypatch.setattr(
        "core_runtime.pack_function_policy.get_approval_manager",
        lambda: _make_approval_manager(
            status=None,
            verify_hash=False,
            is_core=True,
        ),
    )

    assert_pack_function_executable(entry)


def test_grant_config_function_is_rejected_without_grant(tmp_path, monkeypatch):
    function_dir = tmp_path / "fn"
    function_dir.mkdir()
    (function_dir / "main.py").write_text("def run(context, args): return args\n", encoding="utf-8")
    entry = _make_entry(function_dir, grant_config={"allowed": True})
    monkeypatch.setattr("core_runtime.pack_function_runtime.BASE_DIR", tmp_path)

    grant_manager = MagicMock()
    grant_manager.check.return_value = SimpleNamespace(
        allowed=False,
        reason="Permission not granted",
        config={},
    )

    monkeypatch.setattr(
        "core_runtime.pack_function_policy.get_approval_manager",
        lambda: _make_approval_manager(),
    )
    monkeypatch.setattr(
        "core_runtime.pack_function_policy.get_capability_grant_manager",
        lambda: grant_manager,
    )

    with pytest.raises(PermissionError, match="Permission not granted"):
        assert_pack_function_executable(entry)


def test_python_host_function_is_rejected_without_env(tmp_path, monkeypatch):
    function_dir = tmp_path / "fn"
    function_dir.mkdir()
    (function_dir / "main.py").write_text("def run(context, args): return args\n", encoding="utf-8")
    entry = _make_entry(
        function_dir,
        calling_convention="python_host",
        grant_config={"host": True},
    )
    monkeypatch.setattr("core_runtime.pack_function_runtime.BASE_DIR", tmp_path)

    grant_manager = MagicMock()
    grant_manager.check.return_value = SimpleNamespace(
        allowed=True,
        reason="Granted",
        config={"host": True},
    )
    trust_store = MagicMock()
    trust_store.is_loaded.return_value = True
    trust_store.is_trusted.return_value = SimpleNamespace(
        trusted=True,
        reason="Granted",
    )

    monkeypatch.delenv("RUMI_ALLOW_HOST_EXECUTION", raising=False)
    monkeypatch.setattr(
        "core_runtime.pack_function_policy.get_approval_manager",
        lambda: _make_approval_manager(),
    )
    monkeypatch.setattr(
        "core_runtime.pack_function_policy.get_capability_grant_manager",
        lambda: grant_manager,
    )
    monkeypatch.setattr(
        "core_runtime.pack_function_policy.get_capability_trust_store",
        lambda: trust_store,
    )

    with pytest.raises(PermissionError, match="Host execution is disabled"):
        assert_pack_function_executable(entry)


def test_function_entrypoint_path_traversal_is_rejected(tmp_path, monkeypatch):
    root = tmp_path / "root"
    function_dir = root / "pack" / "functions" / "demo"
    function_dir.mkdir(parents=True)
    outside_path = root / "pack" / "outside.py"
    outside_path.write_text("def run(context, args): return args\n", encoding="utf-8")
    entry = _make_entry(function_dir, entrypoint="../../outside.py:run")
    monkeypatch.setattr("core_runtime.pack_function_runtime.BASE_DIR", root)

    monkeypatch.setattr(
        "core_runtime.pack_function_policy.get_approval_manager",
        lambda: _make_approval_manager(is_core=True),
    )

    with pytest.raises(PermissionError, match="Path traversal detected in entrypoint"):
        assert_pack_function_executable(entry)


def test_command_executable_outside_function_boundary_is_rejected(tmp_path, monkeypatch):
    function_dir = tmp_path / "fn"
    function_dir.mkdir()
    outside_bin = tmp_path / "outside-bin"
    outside_bin.write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
    entry = _make_entry(
        function_dir,
        calling_convention="command",
    )
    entry.command = [str(outside_bin)]
    monkeypatch.setattr("core_runtime.pack_function_runtime.BASE_DIR", tmp_path)
    monkeypatch.setattr(
        "core_runtime.pack_function_policy.get_approval_manager",
        lambda: _make_approval_manager(is_core=True),
    )

    with pytest.raises(PermissionError, match="Entrypoint escapes function boundary"):
        assert_pack_function_executable(entry)


def test_command_function_requires_absolute_executable_path(tmp_path, monkeypatch):
    function_dir = tmp_path / "fn"
    function_dir.mkdir()
    entry = _make_entry(
        function_dir,
        calling_convention="command",
    )
    entry.command = ["bash", "-lc", "echo hi"]
    monkeypatch.setattr("core_runtime.pack_function_runtime.BASE_DIR", tmp_path)
    monkeypatch.setattr(
        "core_runtime.pack_function_policy.get_approval_manager",
        lambda: _make_approval_manager(is_core=True),
    )

    with pytest.raises(
        PermissionError,
        match="absolute executable path",
    ):
        assert_pack_function_executable(entry)
