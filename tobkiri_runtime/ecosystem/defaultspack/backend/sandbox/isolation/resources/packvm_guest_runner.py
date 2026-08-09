#!/usr/bin/env python3
"""Authenticated artifact staging endpoint for the managed PackVM guest."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys


PROTOCOL = "io.tobkiri.packvm-supervisor.v1"
BUILD_ID = "tobkiri-packvm-runner-2"
ARTIFACT_ROOT = Path("/var/lib/tobkiri-packvm/artifacts")
MAX_REQUEST_BYTES = 700 * 1024 * 1024
MAX_FILES = 10_000
MAX_FILE_BYTES = 128 * 1024 * 1024
MAX_TOTAL_BYTES = 512 * 1024 * 1024
_DIGEST = re.compile(r"^sha256:[a-f0-9]{64}$")
_IDENTIFIER = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")


def main() -> int:
    """Serve one bounded request from stdin and emit one JSON response."""

    try:
        raw = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
        if len(raw) > MAX_REQUEST_BYTES:
            raise ValueError("request exceeds size limit")
        request = json.loads(raw)
        if not isinstance(request, dict):
            raise ValueError("request must be an object")
        operation = request.get("operation")
        if operation == "doctor":
            response = {
                "ok": True,
                "protocol": PROTOCOL,
                "build_id": BUILD_ID,
            }
        elif operation == "materialize":
            response = _materialize(request)
        elif (
            operation == "invoke"
            and request.get("contract_id") == "io.tobkiri.packvm.attestation.v1"
            and request.get("operation_id") == "challenge"
            and isinstance(request.get("payload"), dict)
            and isinstance(request["payload"].get("challenge"), str)
            and len(request["payload"]["challenge"]) == 64
        ):
            challenge = request["payload"]["challenge"]
            response = {
                "ok": True,
                "protocol": PROTOCOL,
                "payload": {
                    "challenge_digest": _sha256(challenge.encode()),
                },
            }
        elif operation == "invoke":
            identity = _verify_invocation_artifact(request)
            response = {
                "ok": False,
                "error": "packvm_execution_abi_unavailable",
                "protocol": PROTOCOL,
                "guest_artifact_identity": identity,
            }
        else:
            raise ValueError("unsupported operation")
    except (binascii.Error, OSError, ValueError, json.JSONDecodeError) as exc:
        response = {
            "ok": False,
            "error": "invalid_request",
            "message": str(exc),
            "protocol": PROTOCOL,
        }
    sys.stdout.write(json.dumps(response, sort_keys=True, separators=(",", ":")))
    sys.stdout.write("\n")
    return 0


def _materialize(request: dict[str, object]) -> dict[str, object]:
    if os.geteuid() != 0:
        raise ValueError("artifact materialization requires the root-owned supervisor")
    required = {
        "operation",
        "pack_id",
        "artifact_digest",
        "function_id",
        "implementation_digest",
        "implementation_path",
        "materialization_digest",
        "materialization_nonce",
        "files",
    }
    if set(request) != required:
        raise ValueError("artifact materialization fields are invalid")
    pack_id = _identifier(request["pack_id"], "pack_id")
    function_id = _identifier(request["function_id"], "function_id")
    artifact_digest = _digest(request["artifact_digest"], "artifact_digest")
    implementation_digest = _digest(
        request["implementation_digest"], "implementation_digest"
    )
    materialization_digest = _digest(
        request["materialization_digest"], "materialization_digest"
    )
    implementation_path = _relative_path(request["implementation_path"])
    nonce = str(request["materialization_nonce"])
    if len(nonce) != 64 or any(character not in "0123456789abcdef" for character in nonce):
        raise ValueError("materialization nonce is invalid")
    raw_files = request["files"]
    if not isinstance(raw_files, list) or not raw_files or len(raw_files) > MAX_FILES:
        raise ValueError("artifact file inventory is invalid")

    files: list[tuple[str, str, bool, bytes]] = []
    seen: set[str] = set()
    total = 0
    for raw_file in raw_files:
        if not isinstance(raw_file, dict) or set(raw_file) != {
            "path",
            "digest",
            "executable",
            "content",
        }:
            raise ValueError("artifact file entry is invalid")
        path = _relative_path(raw_file["path"])
        if path in seen:
            raise ValueError("artifact file path is duplicated")
        seen.add(path)
        digest = _digest(raw_file["digest"], "file digest")
        executable = raw_file["executable"]
        if not isinstance(executable, bool):
            raise ValueError("artifact executable flag is invalid")
        encoded = raw_file["content"]
        if not isinstance(encoded, str):
            raise ValueError("artifact file content is invalid")
        content = base64.b64decode(encoded, validate=True)
        if len(content) > MAX_FILE_BYTES or _sha256(content) != digest:
            raise ValueError("artifact file content digest mismatch")
        total += len(content)
        if total > MAX_TOTAL_BYTES:
            raise ValueError("artifact exceeds total size limit")
        files.append((path, digest, executable, content))
    implementations = [item for item in files if item[0] == implementation_path]
    if len(implementations) != 1 or implementations[0][1] != implementation_digest:
        raise ValueError("artifact implementation identity is unavailable")
    expected_materialization = _canonical_digest(
        {
            "pack_id": pack_id,
            "artifact_digest": artifact_digest,
            "function_id": function_id,
            "implementation_digest": implementation_digest,
            "implementation_path": implementation_path,
            "files": [
                {
                    "path": path,
                    "digest": digest,
                    "executable": executable,
                    "size": len(content),
                }
                for path, digest, executable, content in files
            ],
        }
    )
    if materialization_digest != expected_materialization:
        raise ValueError("artifact materialization digest mismatch")

    artifact_hex = artifact_digest.removeprefix("sha256:")
    materialization_hex = materialization_digest.removeprefix("sha256:")
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(ARTIFACT_ROOT, 0o700)
    parent = ARTIFACT_ROOT / artifact_hex
    parent.mkdir(mode=0o700, exist_ok=True)
    if parent.is_symlink():
        raise ValueError("artifact staging parent is symlinked")
    target = parent / materialization_hex
    if target.exists():
        manifest = _load_manifest(target)
        if manifest.get("materialization_nonce") == nonce:
            raise ValueError("artifact materialization replay")
        identity = _verify_staged_artifact(
            target,
            artifact_digest,
            materialization_digest,
        )
        return {
            "ok": True,
            "protocol": PROTOCOL,
            "artifact_digest": artifact_digest,
            "materialization_digest": materialization_digest,
            "guest_artifact_identity": identity,
        }

    temporary = parent / f".{materialization_hex}.{nonce}.tmp"
    if temporary.exists() or temporary.is_symlink():
        raise ValueError("artifact staging temporary path already exists")
    temporary.mkdir(mode=0o700)
    try:
        for path, digest, executable, content in files:
            destination = temporary.joinpath(*PurePosixPath(path).parts)
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            descriptor = os.open(
                destination,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o500 if executable else 0o400,
            )
            try:
                offset = 0
                while offset < len(content):
                    written = os.write(descriptor, content[offset:])
                    if written <= 0:
                        raise OSError("artifact staging write made no progress")
                    offset += written
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            os.chmod(destination, 0o500 if executable else 0o400)
            if _sha256(destination.read_bytes()) != digest:
                raise ValueError("artifact changed while staging")
        manifest = {
            "version": "io.tobkiri.packvm-materialization.v1",
            "pack_id": pack_id,
            "artifact_digest": artifact_digest,
            "function_id": function_id,
            "implementation_digest": implementation_digest,
            "implementation_path": implementation_path,
            "materialization_digest": materialization_digest,
            "materialization_nonce": nonce,
            "files": [
                {
                    "path": path,
                    "digest": digest,
                    "executable": executable,
                    "size": len(content),
                }
                for path, digest, executable, content in files
            ],
        }
        manifest_path = temporary / ".tobkiri-materialization.json"
        manifest_path.write_text(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        os.chmod(manifest_path, 0o400)
        for current, directories, _names in os.walk(temporary, topdown=False):
            for directory in directories:
                os.chmod(Path(current) / directory, 0o500)
            if Path(current) != temporary:
                os.chmod(current, 0o500)
        os.replace(temporary, target)
        os.chmod(target, 0o500)
    finally:
        if temporary.exists():
            _make_tree_writable(temporary)
            shutil.rmtree(temporary)
    identity = _verify_staged_artifact(target, artifact_digest, materialization_digest)
    return {
        "ok": True,
        "protocol": PROTOCOL,
        "artifact_digest": artifact_digest,
        "materialization_digest": materialization_digest,
        "guest_artifact_identity": identity,
    }


def _verify_invocation_artifact(request: dict[str, object]) -> str:
    artifact_digest = _digest(request.get("artifact_digest"), "artifact_digest")
    materialization_digest = _digest(
        request.get("materialization_digest"), "materialization_digest"
    )
    expected_identity = _digest(
        request.get("guest_artifact_identity"), "guest_artifact_identity"
    )
    target = (
        ARTIFACT_ROOT
        / artifact_digest.removeprefix("sha256:")
        / materialization_digest.removeprefix("sha256:")
    )
    identity = _verify_staged_artifact(target, artifact_digest, materialization_digest)
    if identity != expected_identity:
        raise ValueError("guest artifact filesystem identity changed")
    return identity


def _make_tree_writable(root: Path) -> None:
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        os.chmod(current_path, 0o700)
        for directory in directories:
            path = current_path / directory
            if not path.is_symlink():
                os.chmod(path, 0o700)
        for filename in files:
            path = current_path / filename
            if not path.is_symlink():
                os.chmod(path, 0o600)


def _verify_staged_artifact(
    target: Path,
    artifact_digest: str,
    materialization_digest: str,
) -> str:
    metadata = target.lstat()
    if target.is_symlink() or not stat.S_ISDIR(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o500:
        raise ValueError("staged artifact root is unsafe")
    manifest = _load_manifest(target)
    if (
        manifest.get("artifact_digest") != artifact_digest
        or manifest.get("materialization_digest") != materialization_digest
    ):
        raise ValueError("staged artifact identity mismatch")
    files = manifest.get("files")
    if not isinstance(files, list):
        raise ValueError("staged artifact manifest is invalid")
    expected_files = {
        _relative_path(item.get("path"))
        for item in files
        if isinstance(item, dict)
    }
    if len(expected_files) != len(files):
        raise ValueError("staged artifact manifest is invalid")
    expected_directories = {
        parent.as_posix()
        for path in expected_files
        for parent in PurePosixPath(path).parents
        if parent.as_posix() != "."
    }
    actual_files: set[str] = set()
    actual_directories: set[str] = set()
    for current_path, directories, filenames in os.walk(target, followlinks=False):
        current = Path(current_path)
        for directory in directories:
            path = current / directory
            if path.is_symlink() or stat.S_IMODE(path.lstat().st_mode) != 0o500:
                raise ValueError("staged artifact directory is unsafe")
            actual_directories.add(path.relative_to(target).as_posix())
        for filename in filenames:
            path = current / filename
            relative = path.relative_to(target).as_posix()
            if relative != ".tobkiri-materialization.json":
                actual_files.add(relative)
    if actual_files != expected_files or actual_directories != expected_directories:
        raise ValueError("staged artifact file inventory changed")
    for item in files:
        if not isinstance(item, dict):
            raise ValueError("staged artifact manifest is invalid")
        relative = _relative_path(item.get("path"))
        candidate = target.joinpath(*PurePosixPath(relative).parts)
        current = candidate.lstat()
        if candidate.is_symlink() or not stat.S_ISREG(current.st_mode):
            raise ValueError("staged artifact contains an unsafe file")
        expected_mode = 0o500 if item.get("executable") is True else 0o400
        if stat.S_IMODE(current.st_mode) != expected_mode:
            raise ValueError("staged artifact file is not read-only")
        content = candidate.read_bytes()
        if len(content) != item.get("size") or _sha256(content) != item.get("digest"):
            raise ValueError("staged artifact file digest changed")
    return _canonical_digest(
        {
            "artifact_digest": artifact_digest,
            "materialization_digest": materialization_digest,
            "device": int(metadata.st_dev),
            "inode": int(metadata.st_ino),
            "implementation_digest": manifest.get("implementation_digest"),
        }
    )


def _load_manifest(target: Path) -> dict[str, object]:
    path = target / ".tobkiri-materialization.json"
    metadata = path.lstat()
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o400
        or metadata.st_size > MAX_REQUEST_BYTES
    ):
        raise ValueError("staged artifact manifest is unsafe")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        before = os.fstat(descriptor)
        content = os.read(descriptor, MAX_REQUEST_BYTES + 1)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if (
        len(content) > MAX_REQUEST_BYTES
        or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    ):
        raise ValueError("staged artifact manifest changed while reading")
    value = json.loads(content)
    if not isinstance(value, dict):
        raise ValueError("staged artifact manifest is invalid")
    return value


def _relative_path(value: object) -> str:
    path = str(value or "")
    relative = PurePosixPath(path)
    if (
        not path
        or relative.is_absolute()
        or ".." in relative.parts
        or "." in relative.parts
        or "\\" in path
    ):
        raise ValueError("artifact path is unsafe")
    return path


def _identifier(value: object, label: str) -> str:
    normalized = str(value or "")
    if _IDENTIFIER.fullmatch(normalized) is None:
        raise ValueError(f"{label} is invalid")
    return normalized


def _digest(value: object, label: str) -> str:
    normalized = str(value or "")
    if _DIGEST.fullmatch(normalized) is None:
        raise ValueError(f"{label} is invalid")
    return normalized


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return _sha256(encoded)


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
