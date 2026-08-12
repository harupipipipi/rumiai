"""Generate and verify the canonical packaged Defaults source closure.

The manifest is deliberately outside the closure it describes so its own
digest does not create a recursive identity.  Python packaging tests and the
Rust sparse authoritative-source fixture both consume this one file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterator


SOURCE_MANIFEST_FILENAME = "packaged_defaultspack_source_manifest.v1.json"
SOURCE_MANIFEST_SCHEMA = "io.tobkiri.packaged-defaultspack-source.v1"
SOURCE_ROOTS = (
    "scripts",
    "tobkiri_protocol",
    "ecosystem/defaultspack/domain/runtime_v4",
    "ecosystem/defaultspack/v4",
    "ecosystem/defaultspack/runtime",
    "ecosystem/defaultspack/defaultspack",
)
SOURCE_FILES = (
    "ecosystem/defaultspack/pack.v4.json",
    "ecosystem/defaultspack/contracts.v4.json",
    "ecosystem/defaultspack/artifact-index.v4.json",
)
MANIFEST_KEYS = ("schema", "roots", "files")
FILE_KEYS = ("path", "type", "size", "sha256", "executable")
_ROOT = Path(__file__).resolve().parents[1]


def reject_symlink_components(path: Path) -> None:
    """Reject symlinked ancestors before a source or snapshot path is used."""
    absolute = path.expanduser().absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.is_symlink() and current not in {Path("/var"), Path("/tmp")}:
            raise ValueError(f"source snapshot path contains a symlink: {current}")


def _safe_relative_path(value: str) -> str:
    """Normalize and validate a manifest-relative path."""
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or "\x00" in value
        or value.startswith("/")
        or value.startswith("~")
    ):
        raise ValueError(f"unsafe source manifest path: {value!r}")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"unsafe source manifest path: {value!r}")
    return "/".join(parts)


def _digest_file(path: Path) -> str:
    """Hash one regular, non-hardlinked file without following links."""
    metadata = path.stat(follow_symlinks=False)
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"source closure entry is not a regular file: {path}")
    if metadata.st_nlink != 1:
        raise ValueError(f"source closure entry is hardlinked: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    after = path.stat(follow_symlinks=False)
    if (
        after.st_dev != metadata.st_dev
        or after.st_ino != metadata.st_ino
        or after.st_size != metadata.st_size
        or after.st_mtime_ns != metadata.st_mtime_ns
    ):
        raise ValueError(f"source closure entry changed while hashed: {path}")
    return digest.hexdigest()


def _walk_regular_files(
    root: Path,
    *,
    source_root: Path,
    directories: set[str],
) -> Iterator[Path]:
    """Yield every supported entry below one declared closure root."""
    metadata = root.stat(follow_symlinks=False)
    if root.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        raise ValueError(f"source closure root is not a real directory: {root}")
    directories.add(root.relative_to(source_root).as_posix())
    with os.scandir(root) as entries:
        for entry in sorted(entries, key=lambda item: item.name):
            path = Path(entry.path)
            entry_metadata = entry.stat(follow_symlinks=False)
            if entry.is_symlink():
                raise ValueError(f"source closure contains a symlink: {path}")
            if stat.S_ISDIR(entry_metadata.st_mode):
                yield from _walk_regular_files(
                    path,
                    source_root=source_root,
                    directories=directories,
                )
            elif stat.S_ISREG(entry_metadata.st_mode):
                yield path
            else:
                raise ValueError(f"source closure contains a special entry: {path}")


def _required_directories() -> set[str]:
    """Return directories implied by the declared roots and source files."""
    required: set[str] = set()
    for relative in (*SOURCE_ROOTS, *SOURCE_FILES):
        path = PurePosixPath(relative)
        if relative in SOURCE_ROOTS:
            required.add(path.as_posix())
        path = path.parent
        while path != PurePosixPath("."):
            required.add(path.as_posix())
            path = path.parent
    return required


def _declared_paths(root: Path, directories: set[str]) -> Iterator[Path]:
    """Yield the exact regular files declared by the closure definition."""
    seen: set[str] = set()
    for relative in (*SOURCE_ROOTS, *SOURCE_FILES):
        current = (root / relative).parent
        while current != root:
            metadata = current.stat(follow_symlinks=False)
            if current.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
                raise ValueError(f"source closure parent is not a real directory: {current}")
            directories.add(current.relative_to(root).as_posix())
            current = current.parent
    for relative in SOURCE_ROOTS:
        for path in _walk_regular_files(
            root / relative,
            source_root=root,
            directories=directories,
        ):
            normalized = path.relative_to(root).as_posix()
            if normalized in seen:
                continue
            seen.add(normalized)
            yield path
    for relative in SOURCE_FILES:
        path = root / relative
        metadata = path.stat(follow_symlinks=False)
        if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
            raise ValueError(f"source closure file is not regular: {path}")
        if metadata.st_nlink != 1:
            raise ValueError(f"source closure file is hardlinked: {path}")
        if relative not in seen:
            seen.add(relative)
            yield path


def _file_record(root: Path, path: Path) -> dict[str, Any]:
    """Return the deterministic identity record for one source file."""
    metadata = path.stat(follow_symlinks=False)
    return {
        "path": path.relative_to(root).as_posix(),
        "type": "regular-file",
        "size": metadata.st_size,
        "sha256": _digest_file(path),
        "executable": bool(metadata.st_mode & 0o111),
    }


def build_source_manifest(root: Path = _ROOT) -> dict[str, Any]:
    """Build the canonical source-closure manifest for ``root``."""
    directories: set[str] = set()
    records = sorted(
        (
            _file_record(root, path)
            for path in _declared_paths(root, directories)
        ),
        key=lambda item: item["path"],
    )
    if not records:
        raise ValueError("packaged Defaults source closure is empty")
    required_directories = _required_directories()
    for record in records:
        relative = PurePosixPath(str(record["path"])).parent
        while relative != PurePosixPath("."):
            required_directories.add(relative.as_posix())
            relative = relative.parent
    missing_directories = required_directories - directories
    extra_directories = directories - required_directories
    if missing_directories or extra_directories:
        details = []
        if missing_directories:
            details.append(f"missing={sorted(missing_directories)}")
        if extra_directories:
            details.append(f"extra={sorted(extra_directories)}")
        raise ValueError(
            "packaged Defaults source closure directory set differs: "
            + ", ".join(details)
        )
    return {
        "schema": SOURCE_MANIFEST_SCHEMA,
        "roots": list(SOURCE_ROOTS),
        "files": records,
    }


def _validate_manifest(value: Any) -> dict[str, Any]:
    """Validate manifest shape before it controls source traversal."""
    if not isinstance(value, dict) or tuple(value) != MANIFEST_KEYS:
        raise ValueError("source manifest has unexpected top-level fields")
    if value.get("schema") != SOURCE_MANIFEST_SCHEMA:
        raise ValueError("source manifest schema is invalid")
    if value.get("roots") != list(SOURCE_ROOTS):
        raise ValueError("source manifest roots are invalid")
    files = value.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("source manifest files are invalid")
    normalized: list[dict[str, Any]] = []
    paths: set[str] = set()
    allowed = tuple((*SOURCE_ROOTS, *SOURCE_FILES))
    for entry in files:
        if not isinstance(entry, dict) or tuple(entry) != FILE_KEYS:
            raise ValueError("source manifest file fields are invalid")
        path = _safe_relative_path(entry["path"])
        if path in paths or not any(
            path == candidate or path.startswith(f"{candidate}/")
            for candidate in allowed
        ):
            raise ValueError(f"source manifest file path is invalid: {path}")
        if entry["type"] != "regular-file":
            raise ValueError(f"source manifest file type is invalid: {path}")
        if not isinstance(entry["size"], int) or entry["size"] < 0:
            raise ValueError(f"source manifest file size is invalid: {path}")
        digest = entry["sha256"]
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ValueError(f"source manifest file digest is invalid: {path}")
        if not isinstance(entry["executable"], bool):
            raise ValueError(f"source manifest executable flag is invalid: {path}")
        paths.add(path)
        normalized.append(
            {
                "path": path,
                "type": entry["type"],
                "size": entry["size"],
                "sha256": digest,
                "executable": entry["executable"],
            }
        )
    if [entry["path"] for entry in normalized] != sorted(paths):
        raise ValueError("source manifest files are not sorted")
    return {"schema": value["schema"], "roots": value["roots"], "files": normalized}


def load_source_manifest(root: Path = _ROOT) -> dict[str, Any]:
    """Load and strictly validate the checked-in source manifest."""
    path = root / SOURCE_MANIFEST_FILENAME
    metadata = path.stat(follow_symlinks=False)
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
    ):
        raise ValueError(f"source manifest is not a regular file: {path}")
    return _validate_manifest(json.loads(path.read_text(encoding="utf-8")))


def verify_source_closure(root: Path = _ROOT) -> dict[str, Any]:
    """Require exact paths, types, sizes, and digests for the source closure."""
    expected = load_source_manifest(root)
    actual = build_source_manifest(root)
    if actual != expected:
        raise ValueError("packaged Defaults source closure differs from its manifest")
    return expected


def materialize_source_snapshot(
    source_root: Path,
    destination_root: Path,
) -> Path:
    """Copy the verified closure into a non-writable, link-free snapshot root.

    The caller may inspect a checkout once to create this snapshot.  Consumers
    must then launch from the returned root and must not consult the checkout,
    its Git metadata, or ambient import paths again.
    """
    source_root = source_root.expanduser().absolute()
    destination_root = destination_root.expanduser().absolute()
    reject_symlink_components(source_root)
    reject_symlink_components(destination_root.parent)
    if source_root.is_symlink() or not source_root.is_dir():
        raise ValueError(f"source snapshot input is not a real directory: {source_root}")
    if destination_root.exists() or destination_root.is_symlink():
        raise ValueError(f"source snapshot destination already exists: {destination_root}")
    expected = verify_source_closure(source_root)
    destination_root.parent.mkdir(parents=True, exist_ok=True)
    # Build the tree before making its root immutable; otherwise creating the
    # declared children would fail on POSIX once the root loses owner-write.
    destination_root.mkdir(mode=0o755)

    for relative in (*SOURCE_ROOTS, *SOURCE_FILES):
        (destination_root / relative).parent.mkdir(parents=True, exist_ok=True)
    for relative in SOURCE_ROOTS:
        directory = destination_root / relative
        directory.mkdir(parents=True, exist_ok=True)

    source_manifest = source_root / SOURCE_MANIFEST_FILENAME
    destination_manifest = destination_root / SOURCE_MANIFEST_FILENAME
    shutil.copyfile(source_manifest, destination_manifest)
    destination_manifest.chmod(0o444)

    for entry in expected["files"]:
        relative = _safe_relative_path(str(entry["path"]))
        source = source_root / relative
        destination = destination_root / relative
        metadata = source.stat(follow_symlinks=False)
        if (
            source.is_symlink()
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
        ):
            raise ValueError(f"source snapshot input entry is unsafe: {source}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        destination.chmod(stat.S_IMODE(metadata.st_mode) & ~0o222)
        copied = destination.stat(follow_symlinks=False)
        if copied.st_nlink != 1 or not stat.S_ISREG(copied.st_mode):
            raise ValueError(f"source snapshot output entry is unsafe: {destination}")

    for path in destination_root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"source snapshot output contains a symlink: {path}")
        if path.is_dir():
            path.chmod(0o555)
    destination_root.chmod(0o555)
    verify_source_closure(destination_root)
    return destination_root


def write_source_manifest(root: Path = _ROOT) -> None:
    """Atomically write the deterministic source manifest."""
    path = root / SOURCE_MANIFEST_FILENAME
    payload = json.dumps(build_source_manifest(root), indent=2, ensure_ascii=False) + "\n"
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=root, prefix=f".{path.name}.", delete=False
        ) as output:
            temporary = Path(output.name)
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        temporary.chmod(0o444)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def main() -> int:
    """Check or regenerate the canonical source manifest."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=_ROOT)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if args.check == args.write:
        parser.error("choose exactly one of --check or --write")
    if args.write:
        write_source_manifest(args.root.resolve())
        return 0
    verify_source_closure(args.root.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
