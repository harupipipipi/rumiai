"""Tests for formal Python/Git executable identity binding."""

from __future__ import annotations

import hashlib
import importlib.util
import os
import sys
from pathlib import Path

import pytest


_SCRIPT = Path(__file__).resolve().parents[1] / "packaging_toolchain_identity.py"
_SPEC = importlib.util.spec_from_file_location("packaging_toolchain_identity_test", _SCRIPT)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"cannot load packaging identity script: {_SCRIPT}")
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)

ToolIdentityError = _MODULE.ToolIdentityError
bind_toolchain = _MODULE.bind_toolchain
environment_lines = _MODULE.environment_lines
write_environment_file = _MODULE.write_environment_file


def _executable(path: Path, payload: bytes = b"tool fixture") -> Path:
    path.write_bytes(payload)
    path.chmod(0o555)
    return path


def test_explicit_tool_identities_are_absolute_and_digest_bound(tmp_path: Path) -> None:
    """The binder emits exact raw digests for the explicit executable inputs."""
    python = _executable(tmp_path / "python")
    git = _executable(tmp_path / "git")
    identities = bind_toolchain(python=os.fspath(python), git=os.fspath(git))

    assert identities["python"].path == python
    assert identities["git"].path == git
    assert identities["python"].sha256 == hashlib.sha256(python.read_bytes()).hexdigest()
    assert identities["git"].sha256 == hashlib.sha256(git.read_bytes()).hexdigest()
    output = environment_lines(identities)
    assert "sha256:" not in output
    assert "TOBKIRI_PACKAGING_PYTHON=" in output
    assert "TOBKIRI_PACKAGING_GIT=" in output


@pytest.mark.parametrize("value", ["python", "relative/tool", ""])
def test_nonabsolute_or_missing_explicit_tools_are_rejected(
    tmp_path: Path, value: str
) -> None:
    """Formal tool inputs cannot silently fall back to PATH."""
    python = value or os.fspath(tmp_path / "missing-python")
    git = os.fspath(tmp_path / "missing-git")
    with pytest.raises(ToolIdentityError):
        bind_toolchain(python=python, git=git)


def test_symlink_and_writable_tools_are_rejected(tmp_path: Path) -> None:
    """The formal input itself must be a stable non-writable regular file."""
    target = _executable(tmp_path / "target")
    symlink = tmp_path / "symlink"
    symlink.symlink_to(target)
    with pytest.raises(ToolIdentityError):
        bind_toolchain(python=os.fspath(symlink), git=os.fspath(target))

    target.chmod(0o775)
    with pytest.raises(ToolIdentityError):
        bind_toolchain(python=os.fspath(target), git=os.fspath(target))


def test_environment_output_is_atomic_and_rejects_symlink(tmp_path: Path) -> None:
    """The exported formal input cannot overwrite a linked destination."""
    target = tmp_path / "env"
    write_environment_file(target, "TOBKIRI_PACKAGING_PYTHON=/x\n")
    assert target.read_text(encoding="utf-8") == "TOBKIRI_PACKAGING_PYTHON=/x\n"

    linked = tmp_path / "linked"
    linked_target = tmp_path / "linked-target"
    linked_target.write_text("keep", encoding="utf-8")
    linked.symlink_to(linked_target)
    with pytest.raises(ToolIdentityError):
        write_environment_file(linked, "TOBKIRI_PACKAGING_PYTHON=/evil\n")
    assert linked_target.read_text(encoding="utf-8") == "keep"
