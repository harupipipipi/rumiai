#!/usr/bin/env python3
"""Prepare trusted runtime tools for Tobkiri Launcher development and release builds."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
TAURI_TARGET_ENV = "TAURI_ENV_TARGET_TRIPLE"
UV_PATH_ENV = "RUMI_UV_PATH"
SOURCE_PROVENANCE_FILENAME = "packaging-source-provenance.v1.json"
ISOLATED_MODULE_CODE = (
    "import runpy,sys;root=sys.argv[1];name=sys.argv[2];"
    "sys.path.insert(0,root);sys.argv=[name,*sys.argv[3:]];"
    "runpy.run_module(name,run_name='__main__',alter_sys=True)"
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("dev", "release"),
        required=True,
        help=(
            "Prepare a developer-managed uv for a checkout, or verified bundled tools "
            "for release."
        ),
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root. Defaults to this script's repository.",
    )
    parser.add_argument(
        "--target",
        help=f"Rust target triple. Defaults to ${TAURI_TARGET_ENV}, then the host target.",
    )
    return parser.parse_args(argv)


def host_target() -> str:
    machine = platform.machine().lower()
    if machine in {"amd64", "x86_64"}:
        arch = "x86_64"
    elif machine in {"arm64", "aarch64"}:
        arch = "aarch64"
    else:
        raise RuntimeError(
            "Unsupported host architecture for Tobkiri Launcher: "
            f"{machine or '<unknown>'}"
        )

    if sys.platform == "win32":
        return f"{arch}-pc-windows-msvc"
    if sys.platform == "darwin":
        return f"{arch}-apple-darwin"
    if sys.platform.startswith("linux"):
        return f"{arch}-unknown-linux-gnu"
    raise RuntimeError(f"Unsupported host platform for Tobkiri Launcher: {sys.platform}")


def resolve_target(explicit: str | None, environ: Mapping[str, str] = os.environ) -> str:
    return explicit or environ.get(TAURI_TARGET_ENV) or host_target()


def is_windows_target(target: str) -> bool:
    return "windows" in target or target.endswith("-msvc")


def uv_binary_name(target: str) -> str:
    return "uv.exe" if is_windows_target(target) else "uv"


def repo_venv_uv_path(repo_root: Path, target: str) -> Path:
    if is_windows_target(target):
        return repo_root / ".venv" / "Scripts" / "uv.exe"
    return repo_root / ".venv" / "bin" / "uv"


def bundled_uv_path(repo_root: Path, target: str) -> Path:
    return repo_root / "tobkiri_runtime" / "bundled" / uv_binary_name(target)


def resolve_dev_uv_source(
    repo_root: Path,
    target: str,
    environ: Mapping[str, str] = os.environ,
) -> Path | None:
    configured = environ.get(UV_PATH_ENV)
    candidates: list[Path] = []
    if configured:
        configured_path = Path(configured).expanduser()
        if not configured_path.is_absolute():
            configured_path = repo_root / configured_path
        candidates.append(configured_path)
    candidates.append(repo_venv_uv_path(repo_root, target))

    for candidate in candidates:
        try:
            _require_regular_file(candidate, "development uv candidate")
        except FileNotFoundError:
            continue
        else:
            return candidate.resolve()

    found = shutil.which(uv_binary_name(target)) or shutil.which("uv")
    if not found:
        return None
    path = Path(found)
    _require_regular_file(path, "development uv executable")
    return path.resolve()


def run_command(
    command: Sequence[str | os.PathLike[str]],
    *,
    cwd: Path | None = None,
    capture_output: bool = False,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [os.fspath(part) for part in command],
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture_output else None,
        stderr=subprocess.PIPE if capture_output else None,
        env=None if env is None else dict(env),
    )


DEVELOPMENT_VENV_PROBE = (
    "import sys; print(sys.prefix); print(sys.base_prefix); "
    "print(sys.implementation.name)"
)


def _require_regular_file(path: Path, label: str) -> os.stat_result:
    """Return metadata for a regular, non-symlink, single-link file."""
    metadata = path.stat(follow_symlinks=False)
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise RuntimeError(f"{label} must be a regular file: {path}")
    if getattr(metadata, "st_nlink", 1) != 1:
        raise RuntimeError(f"{label} must not be hardlinked: {path}")
    return metadata


def _require_directory(path: Path, label: str) -> os.stat_result:
    """Return metadata for a real directory without following a symlink."""
    metadata = path.stat(follow_symlinks=False)
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise RuntimeError(f"{label} must be a real directory: {path}")
    return metadata


def _ensure_safe_output_file(path: Path, label: str) -> None:
    """Reject an unsafe existing output before an atomic replacement."""
    try:
        _require_regular_file(path, label)
    except FileNotFoundError:
        return


def _remove_generated_directory(path: Path, label: str) -> None:
    """Remove a generated directory only when its root is a real directory."""
    try:
        _require_directory(path, label)
    except FileNotFoundError:
        return
    shutil.rmtree(path)


def _copy_verified_tree(source: Path, destination: Path, label: str) -> None:
    """Copy a tree while rejecting symlinks, special files, and hardlinks."""
    source_metadata = source.stat(follow_symlinks=False)
    if stat.S_ISLNK(source_metadata.st_mode):
        raise RuntimeError(f"{label} may not contain a symlink: {source}")

    if stat.S_ISDIR(source_metadata.st_mode):
        try:
            destination_metadata = destination.stat(follow_symlinks=False)
        except FileNotFoundError:
            destination.mkdir(parents=True)
        else:
            if stat.S_ISLNK(destination_metadata.st_mode) or not stat.S_ISDIR(
                destination_metadata.st_mode
            ):
                raise RuntimeError(f"unsafe {label} destination: {destination}")
        for child in sorted(source.iterdir(), key=lambda item: item.name):
            _copy_verified_tree(child, destination / child.name, label)
        shutil.copystat(source, destination, follow_symlinks=False)
        return

    _require_regular_file(source, label)
    _ensure_safe_output_file(destination, f"{label} destination")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _development_venv_python_path(repo_root: Path, target: str) -> Path:
    """Return the platform-specific Python launcher in the checkout venv."""
    relative = "Scripts/python.exe" if is_windows_target(target) else "bin/python3"
    return repo_root / ".venv" / relative


def _verified_venv_symlink(path: Path, label: str) -> Path:
    """Resolve a venv launcher symlink and verify its final file identity."""
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise RuntimeError(f"{label} symlink cannot be resolved: {path}: {exc}") from exc
    _require_regular_file(resolved, label)
    return resolved


def _development_site_packages(venv_root: Path, target: str) -> Path:
    """Find the one real site-packages directory in a verified venv."""
    if is_windows_target(target):
        site_packages = venv_root / "Lib" / "site-packages"
        _require_directory(site_packages, "development venv site-packages")
        return site_packages

    lib_root = venv_root / "lib"
    _require_directory(lib_root, "development venv lib directory")
    candidates: list[Path] = []
    for child in sorted(lib_root.iterdir(), key=lambda item: item.name):
        metadata = child.stat(follow_symlinks=False)
        if stat.S_ISLNK(metadata.st_mode):
            raise RuntimeError(f"development venv lib entry may not be a symlink: {child}")
        if stat.S_ISDIR(metadata.st_mode) and child.name.startswith("python"):
            candidate = child / "site-packages"
            try:
                _require_directory(candidate, "development venv site-packages")
            except FileNotFoundError:
                continue
            candidates.append(candidate)
    if len(candidates) != 1:
        raise RuntimeError(
            "development venv must contain exactly one Python site-packages directory "
            f"below {lib_root}"
        )
    return candidates[0]


def _validate_development_venv_tree(venv_root: Path, python_path: Path) -> None:
    """Validate every venv entry before it is copied into a debug bundle."""
    allowed_launcher_dir = python_path.parent
    for current, directories, files in os.walk(venv_root, followlinks=False):
        current_path = Path(current)
        for name in directories:
            path = current_path / name
            metadata = path.stat(follow_symlinks=False)
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                raise RuntimeError(f"development venv directory is unsafe: {path}")
        for name in files:
            path = current_path / name
            metadata = path.stat(follow_symlinks=False)
            if stat.S_ISLNK(metadata.st_mode):
                if path.parent != allowed_launcher_dir or not name.startswith("python"):
                    raise RuntimeError(f"development venv symlink is not a Python launcher: {path}")
                _verified_venv_symlink(path, "development venv Python launcher")
            elif stat.S_ISREG(metadata.st_mode):
                _require_regular_file(path, "development venv file")
            else:
                raise RuntimeError(f"development venv contains an unsupported entry: {path}")


def verify_development_venv(repo_root: Path, target: str) -> Path:
    """Verify the existing checkout venv and return its original launcher path."""
    venv_root = repo_root / ".venv"
    _require_directory(venv_root, "development Python environment")

    config_path = venv_root / "pyvenv.cfg"
    _require_regular_file(config_path, "development venv configuration")
    try:
        config_lines = config_path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"development venv configuration is not UTF-8: {config_path}") from exc
    config: dict[str, str] = {}
    for line in config_lines:
        if not line.strip():
            continue
        if "=" not in line:
            raise RuntimeError(f"development venv configuration is malformed: {config_path}")
        key, value = (part.strip() for part in line.split("=", 1))
        if not key or key in config:
            raise RuntimeError(f"development venv configuration has duplicate keys: {config_path}")
        config[key] = value
    if config.get("implementation", "").casefold() != "cpython":
        raise RuntimeError("development venv must use CPython")
    if config.get("include-system-site-packages", "").casefold() != "false":
        raise RuntimeError("development venv must disable system site-packages")
    if not config.get("home"):
        raise RuntimeError("development venv configuration has no interpreter home")
    if not re.fullmatch(r"\d+(?:\.\d+)+", config.get("version_info", "")):
        raise RuntimeError("development venv configuration has an invalid version")

    python_path = _development_venv_python_path(repo_root, target)
    python_metadata = python_path.stat(follow_symlinks=False)
    if stat.S_ISLNK(python_metadata.st_mode):
        _verified_venv_symlink(python_path, "development venv Python launcher")
    else:
        _require_regular_file(python_path, "development venv Python launcher")
    if not is_windows_target(target) and not os.access(python_path, os.X_OK):
        raise RuntimeError(f"development venv Python launcher is not executable: {python_path}")

    _development_site_packages(venv_root, target)
    _validate_development_venv_tree(venv_root, python_path)
    try:
        result = run_command(
            [python_path, "-I", "-B", "-c", DEVELOPMENT_VENV_PROBE],
            cwd=repo_root,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(f"development venv Python launcher failed: {python_path}") from exc
    output = (result.stdout or "").splitlines()
    if len(output) != 3:
        raise RuntimeError(f"development venv Python probe returned invalid output: {python_path}")
    prefix, base_prefix, implementation = output
    if Path(prefix).resolve() != venv_root.resolve():
        raise RuntimeError(f"development venv Python prefix is not the checkout venv: {python_path}")
    if Path(base_prefix).resolve() == venv_root.resolve():
        raise RuntimeError(f"development venv Python is not isolated from its base interpreter: {python_path}")
    if implementation.casefold() != "cpython":
        raise RuntimeError(f"development venv Python implementation is not CPython: {python_path}")
    return python_path


def verify_uv_binary(path: Path) -> str:
    try:
        result = run_command([path, "--version"], capture_output=True)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        suffix = f": {detail}" if detail else ""
        raise RuntimeError(
            f"uv binary exited with status {exc.returncode}: {path}{suffix}"
        ) from exc
    except OSError as exc:
        raise RuntimeError(f"uv binary is not executable: {path}: {exc}") from exc

    version = (result.stdout or "").strip()
    if not version:
        raise RuntimeError(f"uv binary did not report a version: {path}")
    return version


def copy_dev_uv(source: Path, destination: Path) -> None:
    """Copy one verified development executable into the bundled tools root."""
    _require_regular_file(source, "development uv source")
    _ensure_safe_output_file(destination, "development uv destination")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() == destination.resolve():
        return

    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    try:
        _require_regular_file(temporary, "development uv temporary destination")
    except FileNotFoundError:
        pass
    else:
        temporary.unlink()
    try:
        shutil.copy2(source, temporary)
        if os.name != "nt":
            temporary.chmod(
                temporary.stat().st_mode
                | stat.S_IWUSR
                | stat.S_IXUSR
                | stat.S_IXGRP
                | stat.S_IXOTH
            )
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def prepare_dev(repo_root: Path, target: str) -> Path:
    destination = bundled_uv_path(repo_root, target)
    source = resolve_dev_uv_source(repo_root, target)

    if source is None:
        try:
            _require_regular_file(destination, "existing development uv")
        except FileNotFoundError:
            pass
        else:
            verify_uv_binary(destination)
            print(f"Using existing development uv at {destination}")
            return destination
        expected = repo_venv_uv_path(repo_root, target)
        raise RuntimeError(
            "No trusted development uv binary was found. "
            f"Install development dependencies so {expected} exists, set {UV_PATH_ENV}, "
            "or install uv on PATH."
        )

    source_version = verify_uv_binary(source)
    copy_dev_uv(source, destination)
    staged_version = verify_uv_binary(destination)
    if staged_version != source_version:
        destination.unlink(missing_ok=True)
        raise RuntimeError(
            "Staged development uv reported a different version: "
            f"source={source_version!r}, staged={staged_version!r}"
        )
    print(f"Prepared development uv at {destination} from {source} ({staged_version})")
    return destination


def _target_shell_spec(repo_root: Path, target: str) -> dict[str, str | Path]:
    target_root = repo_root / "tobkiri_launcher" / "src-tauri" / "target" / target / "debug"
    if target == "aarch64-apple-darwin":
        platform_name, architecture = "macos", "arm64"
    elif target == "x86_64-apple-darwin":
        platform_name, architecture = "macos", "x86_64"
    elif target == "x86_64-unknown-linux-gnu":
        platform_name, architecture = "linux", "x86_64"
    elif target == "aarch64-unknown-linux-gnu":
        platform_name, architecture = "linux", "arm64"
    elif target == "x86_64-pc-windows-msvc":
        platform_name, architecture = "windows", "x86_64"
    else:
        raise RuntimeError(f"Unsupported development Shell target: {target}")

    if platform_name == "macos":
        artifact = target_root / "bundle" / "macos" / "Tobkiri.app"
        return {
            "platform": platform_name,
            "architecture": architecture,
            "bundle": "app",
            "artifact": artifact,
            "relative_path": "Tobkiri.app",
            "entrypoint": "Tobkiri.app/Contents/MacOS/tobkiri-shell",
        }
    if platform_name == "linux":
        artifact_dir = target_root / "bundle" / "appimage"
        candidates = sorted(artifact_dir.glob("*.AppImage"))
        artifact = candidates[0] if len(candidates) == 1 else artifact_dir / "Tobkiri.AppImage"
        return {
            "platform": platform_name,
            "architecture": architecture,
            "bundle": "appimage",
            "artifact": artifact,
            "relative_path": "Tobkiri.AppImage",
            "entrypoint": "Tobkiri.AppImage",
        }
    artifact = target_root / "tobkiri-shell.exe"
    return {
        "platform": platform_name,
        "architecture": architecture,
        "bundle": "nsis",
        "artifact": artifact,
        "relative_path": "tobkiri-shell.exe",
        "entrypoint": "tobkiri-shell.exe",
    }


def sign_development_macos_app(application: Path) -> None:
    """Give the checkout Shell a complete, launchable ad-hoc bundle signature."""
    if sys.platform != "darwin":
        return
    run_command(
        [
            "/usr/bin/codesign",
            "--force",
            "--sign",
            "-",
            "--timestamp=none",
            application,
        ]
    )
    run_command(
        [
            "/usr/bin/codesign",
            "--verify",
            "--strict",
            "--all-architectures",
            application,
        ]
    )


def prepare_dev_pack_shell(repo_root: Path, target: str) -> Path:
    manifest = repo_root / "pack-shell" / "Cargo.toml"
    run_command(
        ["cargo", "build", "--target", target, "--manifest-path", manifest],
        cwd=repo_root,
    )
    binary_name = "pack-shell.exe" if is_windows_target(target) else "pack-shell"
    binary = repo_root / "pack-shell" / "target" / target / "debug" / binary_name
    _require_regular_file(binary, "development pack-shell")
    digest_path = binary.with_name(f"{binary.name}.sha256")
    _ensure_safe_output_file(digest_path, "development pack-shell digest")
    digest_path.write_text(
        hashlib.sha256(binary.read_bytes()).hexdigest() + "\n", encoding="ascii"
    )
    bundled_root = repo_root / "tobkiri_runtime" / "bundled"
    bundled_root.mkdir(parents=True, exist_ok=True)
    copy_dev_uv(binary, bundled_root / binary_name)
    presentation_catalog = (
        repo_root
        / "tobkiri_launcher"
        / "src-tauri"
        / "bundled"
        / "presentation_catalog.json"
    )
    _require_regular_file(presentation_catalog, "Launcher presentation catalog")
    _ensure_safe_output_file(
        bundled_root / "presentation_catalog.json",
        "development presentation catalog destination",
    )
    shutil.copy2(presentation_catalog, bundled_root / "presentation_catalog.json")
    return binary


def _git_identity(repo_root: Path, revision: str) -> str:
    result = run_command(
        ["git", "rev-parse", "--verify", revision],
        cwd=repo_root,
        capture_output=True,
    )
    identity = result.stdout.strip()
    if len(identity) != 40 or any(character not in "0123456789abcdef" for character in identity):
        raise RuntimeError(f"Git returned an invalid identity for {revision}")
    return identity


def prepare_dev_defaults(repo_root: Path, target: str) -> Path:
    launcher_root = repo_root / "tobkiri_launcher"
    runtime_root = repo_root / "tobkiri_runtime"
    spec = _target_shell_spec(repo_root, target)
    run_command(
        [
            "cargo", "tauri", "build", "--debug", "--target", target,
            "--config", "src-tauri/tauri.shell.conf.json",
            "--bundles", str(spec["bundle"]), "--ci",
        ],
        cwd=launcher_root,
    )
    artifact = Path(spec["artifact"])
    artifact_metadata = artifact.stat(follow_symlinks=False)
    if stat.S_ISLNK(artifact_metadata.st_mode):
        raise RuntimeError(f"Development Tauri Shell may not be a symlink: {artifact}")
    if spec["platform"] == "macos":
        if not stat.S_ISDIR(artifact_metadata.st_mode):
            raise RuntimeError(f"Development Tauri Shell bundle is not a directory: {artifact}")
    elif not stat.S_ISREG(artifact_metadata.st_mode):
        raise RuntimeError(f"Development Tauri Shell artifact is not a file: {artifact}")
    if stat.S_ISREG(artifact_metadata.st_mode):
        _require_regular_file(artifact, "development Tauri Shell artifact")
    if spec["platform"] == "macos":
        # Cargo's linker signature covers only the Mach-O. LaunchServices
        # requires a complete application-bundle signature, even for local
        # unsigned development. Ad-hoc-sign the exact bytes used by both the
        # Launcher and Defaults metadata so developers need no certificate.
        sign_development_macos_app(artifact)

    # The Launcher resolves presentation artifacts beneath its application
    # root.  Keep the unsigned checkout Shell in an ignored development-only
    # location there so a debug Launcher can verify the exact bytes it will
    # launch without weakening packaged release bindings.
    dev_shell_root = runtime_root / "bundled" / "dev-shell"
    _remove_generated_directory(dev_shell_root, "development Shell output")
    dev_shell_root.mkdir(parents=True)
    staged_shell = dev_shell_root / str(spec["relative_path"])
    _copy_verified_tree(artifact, staged_shell, "development Shell artifact")

    output_root = launcher_root / "src-tauri" / "target" / "dev-defaults"
    _remove_generated_directory(output_root, "development Defaults output")
    bundle_root = output_root / "v4"
    artifact_root = output_root / "platform-artifacts"
    _copy_verified_tree(
        runtime_root / "ecosystem" / "defaultspack" / "v4",
        bundle_root,
        "development Defaults bundle",
    )
    artifact_root.mkdir(parents=True)

    manifest = runtime_root / "packaged_defaultspack_source_manifest.v1.json"
    provenance = runtime_root / SOURCE_PROVENANCE_FILENAME
    if provenance.exists() or provenance.is_symlink():
        raise RuntimeError(f"Refusing to replace existing source provenance: {provenance}")
    payload = {
        "schema": "io.tobkiri.packaging-source-provenance.v1",
        "source_commit": _git_identity(repo_root, "HEAD"),
        "source_tree": _git_identity(repo_root, "HEAD^{tree}"),
        "source_clean": True,
        "source_manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
    }
    try:
        provenance.write_text(
            json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8"
        )
        provenance.chmod(0o444)
        python = verify_development_venv(repo_root, target)
        run_command(
            [
                python, "-I", "-B", "-c", ISOLATED_MODULE_CODE,
                runtime_root, "scripts.generate_packaged_defaultspack_v4_bundle",
                "--source-artifact", artifact,
                "--bundle-root", bundle_root,
                "--artifact-root", artifact_root,
                "--relative-path", str(spec["relative_path"]),
                "--entrypoint", str(spec["entrypoint"]),
                "--platform", str(spec["platform"]),
                "--architecture", str(spec["architecture"]),
                "--bundle-identity", "io.tobkiri.shell.tauri",
                "--source-provenance-file", SOURCE_PROVENANCE_FILENAME,
            ],
            cwd=runtime_root,
        )
    finally:
        if provenance.exists():
            provenance.chmod(0o600)
            provenance.unlink()
    print(f"Prepared unsigned development Defaults Profile at {bundle_root}")
    return bundle_root


def prepare_dev_environment(repo_root: Path, target: str) -> None:
    prepare_dev(repo_root, target)
    prepare_dev_pack_shell(repo_root, target)
    prepare_dev_defaults(repo_root, target)


def load_resource_preparer(repo_root: Path) -> ModuleType:
    path = repo_root / ".github" / "scripts" / "prepare_tauri_resources.py"
    spec = importlib.util.spec_from_file_location("prepare_tauri_resources", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load runtime resource preparer: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def remove_existing_staged_uv(repo_root: Path, target: str) -> None:
    """Remove a prior dev-stage binary before the verified release stage."""
    destination = bundled_uv_path(repo_root, target)
    if not destination.exists():
        return
    if destination.is_symlink() or not destination.is_file():
        raise RuntimeError(f"Refusing to replace unsafe staged uv path: {destination}")
    if os.name != "nt":
        destination.chmod(destination.stat().st_mode | stat.S_IWUSR)
    destination.unlink()


def prepare_release(repo_root: Path, target: str) -> None:
    preparer = load_resource_preparer(repo_root)
    if target not in preparer.UV_SHA256_BY_TARGET:
        raise RuntimeError(
            f"No pinned uv checksum is configured for release target {target!r}. "
            "Update prepare_tauri_resources.py before building this target."
        )

    manifest = repo_root / "pack-shell" / "Cargo.toml"
    if not manifest.is_file():
        raise RuntimeError(f"pack-shell manifest was not found: {manifest}")

    run_command(
        [
            "cargo",
            "build",
            "--locked",
            "--release",
            "--target",
            target,
            "--manifest-path",
            manifest,
        ],
        cwd=repo_root,
    )

    preparer.seal_pack_shell_binary(repo_root, target)
    remove_existing_staged_uv(repo_root, target)

    run_command(
        [
            sys.executable,
            repo_root / ".github" / "scripts" / "prepare_tauri_resources.py",
            "--repo-root",
            repo_root,
            "--target",
            target,
            "--uv-version",
            preparer.UV_PINNED_VERSION,
            "--require-runtime-tools",
        ],
        cwd=repo_root,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = args.repo_root.resolve()
    target = resolve_target(args.target)

    try:
        if args.mode == "dev":
            prepare_dev_environment(repo_root, target)
        else:
            prepare_release(repo_root, target)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Tobkiri Launcher runtime preparation failed: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
