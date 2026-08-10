#!/usr/bin/env python3
"""Authenticated artifact staging endpoint for the managed PackVM guest."""

from __future__ import annotations

import base64
import binascii
from collections.abc import Iterator
from contextlib import contextmanager
import fcntl
import hashlib
import hmac
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import signal
import shutil
import stat
import subprocess
import sys
import time


PROTOCOL = "io.tobkiri.packvm-supervisor.v1"
BUILD_ID = "tobkiri-packvm-runner-2"
ARTIFACT_ROOT = Path("/var/lib/tobkiri-packvm/artifacts")
REQUEST_ROOT = Path("/run/tobkiri-packvm/requests")
MAX_REQUEST_BYTES = 700 * 1024 * 1024
MAX_FILES = 10_000
MAX_FILE_BYTES = 128 * 1024 * 1024
MAX_TOTAL_BYTES = 512 * 1024 * 1024
MAX_ARTIFACT_STORAGE_BYTES = 768 * 1024 * 1024
MIN_GUEST_FREE_RESERVE_BYTES = 512 * 1024 * 1024
MAX_ARTIFACT_METADATA_BYTES = 16 * 1024 * 1024
MAX_RESULT_BYTES = 16 * 1024 * 1024
CANCEL_GRACE_SECONDS = 0.25
PACK_UID = 65534
PACK_GID = 65534
_DIGEST = re.compile(r"^sha256:[a-f0-9]{64}$")
_IDENTIFIER = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")


def main() -> int:
    """Serve one bounded request from stdin and emit one JSON response."""

    try:
        if sys.argv[1:]:
            if len(sys.argv) != 3 or sys.argv[1] != "--execute":
                raise ValueError("PackVM runner arguments are invalid")
            return _execute_staged_module(Path(sys.argv[2]))
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
            response = _invoke(request)
        elif operation == "cancel":
            response = _cancel(request)
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


def _invoke(request: dict[str, object]) -> dict[str, object]:
    """Execute one digest-pinned implementation through the finite PackVM ABI."""

    required = {
        "operation",
        "request_id",
        "target_domain",
        "artifact_digest",
        "materialization_digest",
        "guest_artifact_identity",
        "contract_id",
        "contract_version",
        "operation_id",
        "payload",
        "request_digest",
        "deadline_monotonic",
        "cancel_token",
    }
    if set(request) != required:
        raise ValueError("PackVM invocation fields are invalid")
    for field in ("request_id", "target_domain", "contract_version"):
        if not isinstance(request[field], str) or not request[field]:
            raise ValueError(f"PackVM invocation {field} is invalid")
    if not isinstance(request["payload"], dict):
        raise ValueError("PackVM invocation payload must be an object")
    _digest(request["request_digest"], "request_digest")
    if not isinstance(request["deadline_monotonic"], (int, float)):
        raise ValueError("PackVM invocation deadline is invalid")
    cancel_token = str(request["cancel_token"] or "")
    if len(cancel_token) != 64 or any(value not in "0123456789abcdef" for value in cancel_token):
        raise ValueError("PackVM invocation cancel token is invalid")
    if os.geteuid() != 0:
        raise ValueError("PackVM invocation requires the root-owned supervisor")
    identity = _verify_invocation_artifact(request)
    artifact_digest = _digest(request["artifact_digest"], "artifact_digest")
    materialization_digest = _digest(request["materialization_digest"], "materialization_digest")
    target = (
        ARTIFACT_ROOT
        / artifact_digest.removeprefix("sha256:")
        / materialization_digest.removeprefix("sha256:")
    )
    manifest = _load_manifest(target)
    implementation_path = _relative_path(manifest.get("implementation_path"))
    implementation = target.joinpath(*PurePosixPath(implementation_path).parts)
    encoded = json.dumps(
        {
            "contract_id": _identifier(request["contract_id"], "contract_id"),
            "operation_id": _identifier(request["operation_id"], "operation_id"),
            "payload": request["payload"],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    if len(encoded) > MAX_REQUEST_BYTES:
        raise ValueError("PackVM invocation payload exceeds size limit")
    process = subprocess.Popen(
        _sandbox_argv(target, implementation),
        cwd=target,
        env={"PATH": "/usr/bin:/bin"},
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        _register_request(request, process.pid, cancel_token)
    except Exception:
        _terminate_process_group(process.pid)
        process.communicate()
        raise
    try:
        stdout, stderr = process.communicate(encoded, timeout=60.0)
    except subprocess.TimeoutExpired as exc:
        _terminate_process_group(process.pid)
        process.communicate()
        raise ValueError("PackVM invocation timed out") from exc
    finally:
        _unregister_request(str(request["request_id"]), process.pid)
    if process.returncode != 0:
        message = stderr.decode("utf-8", errors="replace")[:1000]
        raise ValueError(message or "PackVM implementation failed")
    if len(stdout) > MAX_RESULT_BYTES:
        raise ValueError("PackVM invocation result exceeds size limit")
    result = json.loads(stdout)
    if not isinstance(result, dict):
        raise ValueError("PackVM implementation result must be an object")
    return {
        "ok": True,
        "protocol": PROTOCOL,
        "guest_artifact_identity": identity,
        "payload": result,
    }


def _execute_staged_module(path: Path) -> int:
    """Private child mode for the explicit staged Python Pack ABI."""

    try:
        if os.geteuid() == 0:
            raise ValueError("PackVM implementation may not execute as root")
        request = json.loads(sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1))
        if not isinstance(request, dict) or set(request) != {
            "contract_id",
            "operation_id",
            "payload",
        }:
            raise ValueError("PackVM child request is invalid")
        specification = importlib.util.spec_from_file_location("_tobkiri_packvm_entry", path)
        if specification is None or specification.loader is None:
            raise ValueError("PackVM implementation cannot be loaded")
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
        operation = getattr(module, "tobkiri_packvm_invoke", None)
        if not callable(operation):
            raise ValueError("PackVM implementation does not export tobkiri_packvm_invoke")
        result = operation(request["operation_id"], request["payload"])
        if not isinstance(result, dict):
            raise ValueError("PackVM implementation result must be an object")
        encoded = json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
        if len(encoded) > MAX_RESULT_BYTES:
            raise ValueError("PackVM implementation result exceeds size limit")
        sys.stdout.buffer.write(encoded)
        return 0
    except Exception as error:
        sys.stderr.write(f"{type(error).__name__}: {error}\n")
        return 1


def _sandbox_argv(target: Path, implementation: Path) -> tuple[str, ...]:
    """Build the mandatory default-deny guest sandbox command."""

    bwrap = shutil.which("bwrap")
    prlimit = shutil.which("prlimit")
    if bwrap is None or prlimit is None:
        raise ValueError("PackVM guest requires bubblewrap and prlimit")
    runner = Path(__file__).resolve()
    relative = implementation.relative_to(target).as_posix()
    command = [
        prlimit,
        "--nproc=64",
        "--as=536870912",
        "--cpu=60",
        "--fsize=16777216",
        "--nofile=64",
        "--",
        bwrap,
        "--die-with-parent",
        "--new-session",
        "--unshare-user",
        "--unshare-pid",
        "--unshare-ipc",
        "--unshare-uts",
        "--unshare-net",
        "--uid",
        str(PACK_UID),
        "--gid",
        str(PACK_GID),
        "--cap-drop",
        "ALL",
    ]
    for system_root in ("/usr", "/bin", "/lib", "/lib64", "/etc"):
        if Path(system_root).exists():
            command.extend(("--ro-bind", system_root, system_root))
    command.extend(
        (
            "--ro-bind",
            str(target),
            "/pack",
            "--ro-bind",
            str(runner),
            "/runner.py",
            "--dev",
            "/dev",
            "--proc",
            "/proc",
            "--tmpfs",
            "/tmp",
            "--tmpfs",
            "/home",
            "--tmpfs",
            "/run",
            "--dir",
            "/var",
            "--clearenv",
            "--setenv",
            "PATH",
            "/usr/bin:/bin",
            "--setenv",
            "HOME",
            "/home/pack",
            "--chdir",
            "/pack",
            "--",
            sys.executable,
            "-I",
            "-S",
            "/runner.py",
            "--execute",
            f"/pack/{relative}",
        )
    )
    return tuple(command)


def _request_path(request_id: str) -> Path:
    return REQUEST_ROOT / hashlib.sha256(request_id.encode()).hexdigest()


def _register_request(
    request: dict[str, object],
    process_group: int,
    cancel_token: str,
) -> None:
    REQUEST_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(REQUEST_ROOT, 0o700)
    record = {
        "request_id": request["request_id"],
        "target_domain": request["target_domain"],
        "guest_artifact_identity": request["guest_artifact_identity"],
        "cancel_token": cancel_token,
        "process_group": process_group,
    }
    path = _request_path(str(request["request_id"]))
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        os.write(descriptor, json.dumps(record, sort_keys=True).encode())
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _unregister_request(request_id: str, process_group: int) -> None:
    path = _request_path(request_id)
    try:
        record = _read_request(path)
        if record.get("process_group") == process_group:
            path.unlink(missing_ok=True)
    except (OSError, ValueError):
        return


def _read_request(path: Path) -> dict[str, object]:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != 0:
            raise ValueError("PackVM request ownership record is unsafe")
        raw = os.read(descriptor, 16 * 1024)
    finally:
        os.close(descriptor)
    value = json.loads(raw)
    if not isinstance(value, dict) or set(value) != {
        "request_id",
        "target_domain",
        "guest_artifact_identity",
        "cancel_token",
        "process_group",
    }:
        raise ValueError("PackVM request ownership record is invalid")
    return value


def _cancel(request: dict[str, object]) -> dict[str, object]:
    required = {
        "operation",
        "request_id",
        "target_domain",
        "guest_artifact_identity",
        "cancel_token",
    }
    if set(request) != required or os.geteuid() != 0:
        raise ValueError("PackVM cancellation fields are invalid")
    request_id = str(request["request_id"] or "")
    if not request_id:
        raise ValueError("PackVM cancellation request_id is invalid")
    record = _read_request(_request_path(request_id))
    for field in ("request_id", "target_domain", "guest_artifact_identity"):
        if not hmac.compare_digest(str(record.get(field) or ""), str(request[field] or "")):
            raise ValueError(f"PackVM cancellation {field} mismatch")
    if not hmac.compare_digest(
        str(record.get("cancel_token") or ""), str(request["cancel_token"] or "")
    ):
        raise ValueError("PackVM cancellation authentication failed")
    process_group = record.get("process_group")
    if not isinstance(process_group, int) or process_group <= 1:
        raise ValueError("PackVM cancellation process group is invalid")
    signals = _terminate_process_group(process_group)
    return {
        "ok": True,
        "protocol": PROTOCOL,
        "operation": "cancel",
        "request_id": request_id,
        "target_domain": request["target_domain"],
        "state": "cancelled",
        "signals": signals,
    }


def _terminate_process_group(process_group: int) -> list[str]:
    signals: list[str] = []
    try:
        os.killpg(process_group, signal.SIGTERM)
        signals.append("TERM")
    except ProcessLookupError:
        return signals
    deadline = time.monotonic() + CANCEL_GRACE_SECONDS
    while time.monotonic() < deadline:
        try:
            os.killpg(process_group, 0)
        except ProcessLookupError:
            return signals
        time.sleep(0.01)
    try:
        os.killpg(process_group, signal.SIGKILL)
        signals.append("KILL")
    except ProcessLookupError:
        pass
    return signals


def _materialize(request: dict[str, object]) -> dict[str, object]:
    if os.geteuid() != 0:
        raise ValueError("artifact materialization requires the root-owned supervisor")
    with _artifact_storage_lock():
        return _materialize_locked(request)


def _materialize_locked(request: dict[str, object]) -> dict[str, object]:
    """Materialize one artifact while holding the cumulative quota lock."""

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
    implementation_digest = _digest(request["implementation_digest"], "implementation_digest")
    materialization_digest = _digest(request["materialization_digest"], "materialization_digest")
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

    stored_bytes = _artifact_storage_bytes()
    projected_bytes = stored_bytes + total + MAX_ARTIFACT_METADATA_BYTES
    if projected_bytes > MAX_ARTIFACT_STORAGE_BYTES:
        raise ValueError(
            "PackVM artifact storage quota exceeded: "
            f"{projected_bytes} bytes projected, "
            f"{MAX_ARTIFACT_STORAGE_BYTES} bytes allowed"
        )
    free_bytes = int(shutil.disk_usage(ARTIFACT_ROOT).free)
    required_free = total + MAX_ARTIFACT_METADATA_BYTES + MIN_GUEST_FREE_RESERVE_BYTES
    if free_bytes < required_free:
        raise ValueError(
            "PackVM guest free space is insufficient: "
            f"{required_free} bytes required, {free_bytes} bytes available"
        )

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
                0o555 if executable else 0o444,
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
            os.chmod(destination, 0o555 if executable else 0o444)
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
        os.chmod(manifest_path, 0o444)
        for current, directories, _names in os.walk(temporary, topdown=False):
            for directory in directories:
                os.chmod(Path(current) / directory, 0o555)
            if Path(current) != temporary:
                os.chmod(current, 0o555)
        os.replace(temporary, target)
        os.chmod(target, 0o555)
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


@contextmanager
def _artifact_storage_lock() -> Iterator[None]:
    """Serialize staging and quota accounting without following links."""

    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    root_metadata = ARTIFACT_ROOT.lstat()
    if ARTIFACT_ROOT.is_symlink() or not stat.S_ISDIR(root_metadata.st_mode):
        raise ValueError("PackVM artifact storage root is unsafe")
    os.chmod(ARTIFACT_ROOT, 0o700)
    lock_path = ARTIFACT_ROOT / ".quota.lock"
    descriptor = os.open(
        lock_path,
        os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ValueError("PackVM artifact quota lock is unsafe")
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def _verify_invocation_artifact(request: dict[str, object]) -> str:
    artifact_digest = _digest(request.get("artifact_digest"), "artifact_digest")
    materialization_digest = _digest(
        request.get("materialization_digest"), "materialization_digest"
    )
    expected_identity = _digest(request.get("guest_artifact_identity"), "guest_artifact_identity")
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


def _artifact_storage_bytes() -> int:
    """Measure retained root-owned artifacts without following filesystem links."""

    if not ARTIFACT_ROOT.exists():
        return 0
    root_metadata = ARTIFACT_ROOT.lstat()
    if ARTIFACT_ROOT.is_symlink() or not stat.S_ISDIR(root_metadata.st_mode):
        raise ValueError("PackVM artifact storage root is unsafe")
    total = 0
    for current, directories, files in os.walk(ARTIFACT_ROOT, followlinks=False):
        current_path = Path(current)
        for directory in directories:
            path = current_path / directory
            metadata = path.lstat()
            if path.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
                raise ValueError("PackVM artifact storage contains an unsafe directory")
        for filename in files:
            path = current_path / filename
            metadata = path.lstat()
            if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
                raise ValueError("PackVM artifact storage contains an unsafe file")
            total += metadata.st_size
            if total > MAX_ARTIFACT_STORAGE_BYTES:
                raise ValueError("PackVM artifact storage quota is already exceeded")
    return total


def _verify_staged_artifact(
    target: Path,
    artifact_digest: str,
    materialization_digest: str,
) -> str:
    metadata = target.lstat()
    if (
        target.is_symlink()
        or not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o555
    ):
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
    expected_files = {_relative_path(item.get("path")) for item in files if isinstance(item, dict)}
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
            if path.is_symlink() or stat.S_IMODE(path.lstat().st_mode) != 0o555:
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
        candidate_metadata = candidate.lstat()
        if candidate.is_symlink() or not stat.S_ISREG(candidate_metadata.st_mode):
            raise ValueError("staged artifact contains an unsafe file")
        expected_mode = 0o555 if item.get("executable") is True else 0o444
        if stat.S_IMODE(candidate_metadata.st_mode) != expected_mode:
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
        or stat.S_IMODE(metadata.st_mode) != 0o444
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
    if len(content) > MAX_REQUEST_BYTES or (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
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
