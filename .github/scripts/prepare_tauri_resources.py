#!/usr/bin/env python3
"""Prepare bundled Rumi runtime resources for the Tauri desktop app."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import time
import tempfile
import urllib.request
import zipfile
from pathlib import Path


APP_SOURCE_DIR = "rumi_ai_1_10"
APP_RESOURCE_DIR = "rumi_viewer/src-tauri/gen/app"

EXCLUDED_DIR_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".rumi_snapshots",
    ".venv",
    "__pycache__",
    "node_modules",
    "target",
    "user_data",
    "userdata",
    "venv",
}
EXCLUDED_SUFFIXES = {
    ".bak",
    ".pyc",
    ".pyo",
    ".zip",
}
EXCLUDED_TOP_LEVEL_DIRS = {
    "tests",
}
GENERATED_RESOURCE_DIRS = (
    "core_runtime/core_pack/core_control_panel/web",
    "ecosystem/defaultspack/ui",
    "bundled",
)
UV_PINNED_VERSION = "0.11.14"
UV_SHA256_BY_TARGET = {
    "aarch64-apple-darwin": "4333af5c0730d94323a7819bbdf87ce92dd07fc857d67fff0059e0fca31b5c02",
    "x86_64-apple-darwin": "9836c1440b0bd6aa5f81793648a339bd01d593b7b8f575de3b855dae4ab64654",
    "x86_64-pc-windows-msvc": "52ba5d19409aaa688a8a1a6ec8dfb6a4817230d20186e75f4006105c3e39a846",
    "x86_64-unknown-linux-gnu": "f3b623eb0e6141a7053d571d59a0bdc341e0f238ea8f5f0b4815ddbec9a2a296",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Repository root. Defaults to this script's repository.",
    )
    parser.add_argument(
        "--target",
        help="Rust/Tauri target triple. When set, stages pack-shell for that target.",
    )
    parser.add_argument(
        "--uv-version",
        help="uv release version to bundle, for example 0.11.14.",
    )
    parser.add_argument(
        "--require-runtime-tools",
        action="store_true",
        help="Fail unless bundled uv and pack-shell are present.",
    )
    return parser.parse_args()


def path_parts(rel: str) -> list[str]:
    return [part for part in rel.replace("\\", "/").split("/") if part]


def should_skip_source_rel(rel_under_app: str) -> bool:
    parts = path_parts(rel_under_app)
    if not parts:
        return True
    if parts[0] in EXCLUDED_TOP_LEVEL_DIRS:
        return True
    if any(part in EXCLUDED_DIR_NAMES for part in parts):
        return True
    path = Path(rel_under_app)
    if path.name == ".DS_Store":
        return True
    return any(path.name.endswith(suffix) for suffix in EXCLUDED_SUFFIXES)


def run_git_ls_files(repo_root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", APP_SOURCE_DIR],
        cwd=repo_root,
        check=True,
        stdout=subprocess.PIPE,
    )
    return [item for item in result.stdout.decode("utf-8").split("\0") if item]


def copy_file(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    mode = src.stat().st_mode
    if mode & stat.S_IXUSR:
        dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def copy_tracked_runtime_files(repo_root: Path, source_root: Path, dest_root: Path) -> int:
    copied = 0
    source_prefix = f"{APP_SOURCE_DIR}/"
    for rel in run_git_ls_files(repo_root):
        if not rel.startswith(source_prefix):
            continue
        rel_under_app = rel[len(source_prefix) :]
        if should_skip_source_rel(rel_under_app):
            continue
        src = repo_root / rel
        if not src.is_file():
            continue
        copy_file(src, dest_root / rel_under_app)
        copied += 1
    return copied


def copy_generated_resource_dirs(source_root: Path, dest_root: Path) -> int:
    copied = 0
    for rel_dir in GENERATED_RESOURCE_DIRS:
        src_dir = source_root / rel_dir
        if not src_dir.exists():
            continue
        for src in src_dir.rglob("*"):
            if not src.is_file():
                continue
            rel_under_app = src.relative_to(source_root).as_posix()
            if should_skip_source_rel(rel_under_app):
                continue
            copy_file(src, dest_root / rel_under_app)
            copied += 1
    return copied


def is_windows_target(target: str) -> bool:
    return "windows" in target or target.endswith("-msvc")


def pack_shell_binary_name(target: str) -> str:
    return "pack-shell.exe" if is_windows_target(target) else "pack-shell"


def uv_binary_name(target: str) -> str:
    return "uv.exe" if is_windows_target(target) else "uv"


def stage_pack_shell(repo_root: Path, source_root: Path, target: str) -> Path:
    binary_name = pack_shell_binary_name(target)
    src = repo_root / "pack-shell" / "target" / target / "release" / binary_name
    if not src.exists():
        raise FileNotFoundError(
            f"pack-shell binary not found at {src}. Build pack-shell before preparing resources."
        )

    dest = source_root / "bundled" / binary_name
    copy_file(src, dest)
    return dest


def download_to_temp(url: str, attempts: int = 15) -> Path:
    suffix = ".zip" if url.endswith(".zip") else ".tar.gz"
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        fd, temp_name = tempfile.mkstemp(prefix="rumi-uv-", suffix=suffix)
        os.close(fd)
        temp_path = Path(temp_name)
        try:
            with urllib.request.urlopen(url, timeout=300) as response:
                if response.status >= 400:
                    raise RuntimeError(f"HTTP {response.status} for {url}")
                with temp_path.open("wb") as out:
                    shutil.copyfileobj(response, out)
            return temp_path
        except Exception as exc:  # pragma: no cover - network retry path
            temp_path.unlink(missing_ok=True)
            last_error = exc
            if attempt < attempts:
                print(f"Download failed for {url} (attempt {attempt}/{attempts}): {exc}", file=sys.stderr)
                time.sleep(min(30, 2 * attempt))
    assert last_error is not None
    raise last_error


def download_text(url: str, attempts: int = 5) -> str:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(url, timeout=300) as response:
                if response.status >= 400:
                    raise RuntimeError(f"HTTP {response.status} for {url}")
                return response.read().decode("utf-8")
        except Exception as exc:  # pragma: no cover - network retry path
            last_error = exc
            if attempt < attempts:
                print(f"Download failed for {url} (attempt {attempt}/{attempts}): {exc}", file=sys.stderr)
                time.sleep(min(30, 2 * attempt))
    assert last_error is not None
    raise last_error


def compute_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def expected_uv_sha256(target: str, version: str) -> str:
    if version != UV_PINNED_VERSION:
        raise RuntimeError(
            "No pinned SHA256 is configured for uv version "
            f"{version}. Update UV_PINNED_VERSION/UV_SHA256_BY_TARGET before bundling."
        )
    try:
        return UV_SHA256_BY_TARGET[target]
    except KeyError as exc:
        raise RuntimeError(
            f"No pinned SHA256 is configured for uv target {target!r}. "
            "Update UV_SHA256_BY_TARGET before bundling."
        ) from exc


def parse_sha256_manifest(text: str, expected_filename: str) -> str:
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split()
        if not parts:
            continue
        checksum = parts[0].lower()
        if len(parts) >= 2:
            filename = parts[-1].lstrip("*")
            if filename != expected_filename:
                raise RuntimeError(
                    f"Checksum manifest filename mismatch: expected {expected_filename}, got {filename}"
                )
        if len(checksum) != 64 or any(ch not in "0123456789abcdef" for ch in checksum):
            raise RuntimeError(f"Checksum manifest did not contain a valid SHA256 for {expected_filename}")
        return checksum
    raise RuntimeError(f"Checksum manifest was empty for {expected_filename}")


def verify_uv_archive_checksum(archive_path: Path, *, target: str, version: str, url: str) -> None:
    pinned_sha256 = expected_uv_sha256(target, version).lower()
    actual_sha256 = compute_sha256(archive_path).lower()
    if actual_sha256 != pinned_sha256:
        raise RuntimeError(
            "uv archive SHA256 mismatch for "
            f"{Path(url).name}: expected {pinned_sha256}, got {actual_sha256}"
        )


def stage_uv(source_root: Path, target: str, version: str) -> Path:
    binary_name = uv_binary_name(target)
    archive_ext = "zip" if is_windows_target(target) else "tar.gz"
    url = f"https://github.com/astral-sh/uv/releases/download/{version}/uv-{target}.{archive_ext}"
    archive_path = download_to_temp(url)
    dest = source_root / "bundled" / binary_name
    dest.parent.mkdir(parents=True, exist_ok=True)
    expected = f"uv-{target}/{binary_name}"

    try:
        verify_uv_archive_checksum(archive_path, target=target, version=version, url=url)
        if archive_ext == "zip":
            with zipfile.ZipFile(archive_path) as archive:
                member_name = expected
                if member_name not in archive.namelist():
                    matches = [
                        name
                        for name in archive.namelist()
                        if Path(name).name == binary_name
                    ]
                    if not matches:
                        raise KeyError(
                            f"{binary_name} was not found in {archive_path}"
                        )
                    member_name = matches[0]
                with archive.open(member_name) as src, dest.open("wb") as out:
                    shutil.copyfileobj(src, out)
        else:
            with tarfile.open(archive_path, "r:gz") as archive:
                try:
                    member = archive.getmember(expected)
                except KeyError:
                    matches = [
                        member
                        for member in archive.getmembers()
                        if Path(member.name).name == binary_name
                    ]
                    if not matches:
                        raise KeyError(
                            f"{binary_name} was not found in {archive_path}"
                        )
                    member = matches[0]
                extracted = archive.extractfile(member)
                if extracted is None:
                    raise RuntimeError(f"{expected} is not a file in {archive_path}")
                with extracted, dest.open("wb") as out:
                    shutil.copyfileobj(extracted, out)
    finally:
        archive_path.unlink(missing_ok=True)

    if not is_windows_target(target):
        dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return dest


def validate_bundle(dest_root: Path, require_runtime_tools: bool, target: str | None) -> None:
    required = [
        Path("app.py"),
        Path("requirements.txt"),
        Path("core_runtime/core_pack/core_control_panel/web/index.html"),
        Path("ecosystem/defaultspack/ecosystem.json"),
        Path("ecosystem/defaultspack/ui/shell.html"),
        Path("ecosystem/defaultspack/ui/shell-app.js"),
    ]
    if require_runtime_tools:
        if not target:
            raise ValueError("--require-runtime-tools needs --target")
        required.extend(
            [
                Path("bundled") / uv_binary_name(target),
                Path("bundled") / pack_shell_binary_name(target),
            ]
        )

    missing = [str(path) for path in required if not (dest_root / path).exists()]
    if missing:
        raise FileNotFoundError("Missing bundled resource(s): " + ", ".join(missing))

    forbidden = []
    for path in dest_root.rglob("*"):
        if path.is_dir() and path.name in EXCLUDED_DIR_NAMES:
            forbidden.append(str(path.relative_to(dest_root)))
    if forbidden:
        raise RuntimeError("Forbidden generated bundle directories: " + ", ".join(forbidden[:20]))


def warn_legacy_defaultspack_app_bundle() -> None:
    legacy_app = Path.home() / "Applications" / "Rumi_Defaultspack.app"
    if not legacy_app.exists():
        return

    launch_script = legacy_app / "Contents" / "MacOS" / "launch"
    script_text = ""
    try:
        script_text = launch_script.read_text(encoding="utf-8")
    except OSError:
        pass

    missing_markers = [
        marker
        for marker in ("--api-token", "--port", "RUMI_LOG_DIR", "RUMI_DEFAULTSPACK_OPEN_BROWSER")
        if marker not in script_text
    ]
    if missing_markers:
        print(
            "warning: legacy Defaultspack app bundle detected at "
            f"{legacy_app}. It is missing current launch markers: "
            f"{', '.join(missing_markers)}. Re-register Defaultspack from Rumi Viewer "
            "or remove the legacy bundle to avoid stale launch/load-failed behavior.",
            file=sys.stderr,
        )
    else:
        print(
            "warning: legacy underscore-named Defaultspack app bundle detected at "
            f"{legacy_app}. Current builds generate 'Rumi Defaultspack.app'; "
            "re-registering from Rumi Viewer will clean up old launch services entries.",
            file=sys.stderr,
        )


def directory_size(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            total += item.stat().st_size
    return total


def format_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024 or unit == "GiB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GiB"


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    source_root = repo_root / APP_SOURCE_DIR
    dest_root = repo_root / APP_RESOURCE_DIR

    if not source_root.joinpath("app.py").exists():
        print(f"Rumi source directory not found: {source_root}", file=sys.stderr)
        return 2

    if args.target:
        staged_pack_shell = stage_pack_shell(repo_root, source_root, args.target)
        print(f"Staged {staged_pack_shell.relative_to(repo_root)}")

    if args.uv_version:
        if not args.target:
            print("--uv-version requires --target", file=sys.stderr)
            return 2
        staged_uv = stage_uv(source_root, args.target, args.uv_version)
        print(f"Staged {staged_uv.relative_to(repo_root)}")

    if dest_root.exists():
        shutil.rmtree(dest_root)
    dest_root.mkdir(parents=True, exist_ok=True)

    tracked_count = copy_tracked_runtime_files(repo_root, source_root, dest_root)
    generated_count = copy_generated_resource_dirs(source_root, dest_root)

    validate_bundle(dest_root, args.require_runtime_tools, args.target)
    warn_legacy_defaultspack_app_bundle()
    print(
        "Prepared "
        f"{APP_RESOURCE_DIR} "
        f"({tracked_count} tracked files, {generated_count} generated files, "
        f"{format_size(directory_size(dest_root))})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
