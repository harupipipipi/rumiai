from __future__ import annotations

from pathlib import Path

from .spec import BubblewrapSandboxSpec


def build_bubblewrap_argv(spec: BubblewrapSandboxSpec) -> list[str]:
    """Build Bubblewrap argv from server-side policy only."""
    root = _existing_dir(spec.immutable_root, "immutable_root")
    workspace = _existing_dir(spec.workspace.source, "workspace")
    argv = [
        "bwrap",
        "--unshare-user",
        "--unshare-pid",
        "--unshare-ipc",
        "--unshare-uts",
        "--new-session",
        "--die-with-parent",
        "--proc",
        "/proc",
        "--tmpfs",
        "/tmp",
        "--tmpfs",
        "/home",
        "--dev",
        "/dev",
        "--ro-bind",
        str(root),
        "/",
    ]
    if not spec.network_enabled:
        argv.append("--unshare-net")
    bind_flag = "--ro-bind" if spec.workspace.read_only else "--bind"
    argv.extend([bind_flag, str(workspace), "/workspace", "--chdir", "/workspace"])
    if spec.seccomp_profile is not None:
        argv.extend(["--seccomp", str(_existing_file(spec.seccomp_profile, "seccomp_profile"))])
    for key, value in sorted((spec.env or {}).items()):
        argv.extend(["--setenv", str(key), str(value)])
    argv.extend(["--", *spec.argv])
    return argv


def _existing_dir(path: Path, label: str) -> Path:
    candidate = Path(path).resolve()
    if not candidate.is_dir():
        raise ValueError(f"{label} must be an existing directory")
    return candidate


def _existing_file(path: Path, label: str) -> Path:
    candidate = Path(path).resolve()
    if not candidate.is_file():
        raise ValueError(f"{label} must be an existing file")
    return candidate
