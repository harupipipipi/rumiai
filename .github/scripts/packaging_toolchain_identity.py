"""Bind the exact executable identities used by Rust packaging callers.

The workflow may use PATH once, during this explicit binding step, to discover
the runner's already-installed tools.  The emitted absolute paths and raw
SHA-256 digests are the formal inputs consumed by build.rs and Rust fixtures;
those consumers never perform PATH lookup or trust PYTHON.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import stat
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


class ToolIdentityError(ValueError):
    """Raised when a packaging executable cannot be bound safely."""


@dataclass(frozen=True)
class ToolIdentity:
    """Canonical identity emitted for one packaging executable."""

    path: Path
    sha256: str


def _file_identity(metadata: os.stat_result) -> tuple[int, int, int, int, int]:
    """Return metadata used to detect replacement while hashing."""
    return (
        getattr(metadata, "st_dev", 0),
        getattr(metadata, "st_ino", 0),
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _regular_executable(path: Path, label: str) -> ToolIdentity:
    """Validate and hash one canonical, non-writable executable."""
    if not path.is_absolute():
        raise ToolIdentityError(f"{label} path must be absolute: {path}")
    try:
        before = path.stat(follow_symlinks=False)
    except OSError as error:
        raise ToolIdentityError(f"{label} cannot be inspected: {path}: {error}") from error
    if path.is_symlink() or not stat.S_ISREG(before.st_mode):
        raise ToolIdentityError(f"{label} is not a regular file: {path}")
    if path.resolve(strict=True) != path:
        raise ToolIdentityError(f"{label} path is not canonical: {path}")
    if not os.access(path, os.X_OK):
        raise ToolIdentityError(f"{label} is not executable: {path}")
    if before.st_mode & 0o022:
        raise ToolIdentityError(f"{label} is writable: {path}")

    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        after = path.stat(follow_symlinks=False)
    except OSError as error:
        raise ToolIdentityError(f"{label} cannot be hashed: {path}: {error}") from error
    if (
        path.is_symlink()
        or not stat.S_ISREG(after.st_mode)
        or _file_identity(before) != _file_identity(after)
    ):
        raise ToolIdentityError(f"{label} changed while hashed: {path}")
    return ToolIdentity(path=path, sha256=digest.hexdigest())


def _resolve_requested(value: str | None, label: str) -> Path:
    """Resolve the one discovery input used only by the explicit binder."""
    if value:
        return Path(value)
    if label == "python":
        return Path(sys.executable)
    discovered = shutil.which("git")
    if discovered is None:
        raise ToolIdentityError("git is unavailable for explicit identity binding")
    return Path(discovered)


def bind_toolchain(
    *,
    python: str | None = None,
    git: str | None = None,
) -> dict[str, ToolIdentity]:
    """Return verified Python and Git identities for formal packaging input."""
    return {
        "python": _regular_executable(_resolve_requested(python, "python"), "Python"),
        "git": _regular_executable(_resolve_requested(git, "git"), "Git"),
    }


def environment_lines(identities: dict[str, ToolIdentity]) -> str:
    """Serialize identities as shell-safe GitHub environment assignments."""
    expected = {"python", "git"}
    if set(identities) != expected:
        raise ToolIdentityError("toolchain identity set is incomplete")
    return (
        f"TOBKIRI_PACKAGING_PYTHON={identities['python'].path}\n"
        f"TOBKIRI_PACKAGING_PYTHON_SHA256={identities['python'].sha256}\n"
        f"TOBKIRI_PACKAGING_GIT={identities['git'].path}\n"
        f"TOBKIRI_PACKAGING_GIT_SHA256={identities['git'].sha256}\n"
    )


def write_environment_file(path: Path, payload: str) -> None:
    """Atomically publish the formal toolchain environment file."""
    if path.exists() or path.is_symlink():
        metadata = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
            raise ToolIdentityError(f"toolchain environment output is unsafe: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as output:
            temporary = Path(output.name)
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main() -> int:
    """Bind and emit the exact Python/Git identities."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--python")
    parser.add_argument("--git")
    parser.add_argument("--env-output", type=Path)
    args = parser.parse_args()
    try:
        payload = environment_lines(bind_toolchain(python=args.python, git=args.git))
        if args.env_output is None:
            sys.stdout.write(payload)
        else:
            write_environment_file(args.env_output, payload)
    except ToolIdentityError as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
