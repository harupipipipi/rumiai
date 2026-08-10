"""Verification of selected packaged Shell/Application artifacts."""

from __future__ import annotations

import hashlib
import plistlib
import subprocess
from pathlib import Path
from typing import Any, Mapping

from .errors import ProtocolError


def artifact_digest(path: Path) -> str:
    """Digest a regular file or a symlink-free artifact tree deterministically."""

    digest = hashlib.sha256()
    if path.is_symlink():
        raise ProtocolError("packaged artifact must not be a symlink")
    if path.is_file():
        digest.update(_stable_read(path))
    elif path.is_dir():
        for item in sorted(path.rglob("*")):
            if item.is_symlink():
                raise ProtocolError("packaged artifact tree contains a symlink")
            if item.is_file():
                relative = item.relative_to(path).as_posix().encode("utf-8")
                digest.update(len(relative).to_bytes(8, "big"))
                digest.update(relative)
                payload = _stable_read(item)
                digest.update(len(payload).to_bytes(8, "big"))
                digest.update(payload)
    else:
        raise ProtocolError("packaged artifact is missing")
    return "sha256:" + digest.hexdigest()


def _stable_read(path: Path) -> bytes:
    """Read one regular file without accepting an identity-changing race."""

    before = path.stat(follow_symlinks=False)
    if not path.is_file() or path.is_symlink():
        raise ProtocolError("packaged artifact member is not a regular file")
    payload = path.read_bytes()
    after = path.stat(follow_symlinks=False)
    def identity(value: Any) -> tuple[int, int, int, int, int]:
        return (
            value.st_dev,
            value.st_ino,
            value.st_mode,
            value.st_size,
            value.st_mtime_ns,
        )
    if identity(before) != identity(after) or len(payload) != after.st_size:
        raise ProtocolError("packaged artifact changed while it was verified")
    return payload


def verify_platform_artifact(
    artifact_root: Path,
    variant: Mapping[str, Any],
    *,
    require_macos_code_signature: bool = False,
) -> Path:
    """Verify path, digest, entrypoint, architecture, and macOS bundle identity."""

    root = artifact_root.resolve(strict=True)
    if artifact_root.is_symlink() or not root.is_dir():
        raise ProtocolError("packaged artifact root must be a real directory")
    relative = Path(str(variant["relative_path"]))
    if relative.is_absolute() or ".." in relative.parts:
        raise ProtocolError("packaged artifact path escapes its root")
    artifact = root / relative
    for parent in (artifact, *artifact.parents):
        if parent == root.parent:
            break
        if parent.is_symlink():
            raise ProtocolError("packaged artifact path contains a symlink")
        if parent == root:
            break
    expected = str(variant["artifact_digest"])
    hexadecimal = expected.removeprefix("sha256:")
    if len(set(hexadecimal)) <= 1:
        raise ProtocolError("packaged artifact uses a sentinel digest")
    if artifact_digest(artifact) != expected:
        raise ProtocolError("packaged artifact digest does not match selected bytes")
    entrypoint = root / Path(str(variant["entrypoint"]))
    try:
        entrypoint.resolve(strict=True).relative_to(artifact.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise ProtocolError("packaged artifact entrypoint is missing or outside artifact") from exc
    if entrypoint.is_symlink() or not entrypoint.is_file():
        raise ProtocolError("packaged artifact entrypoint is not a regular file")
    if str(variant["platform"]) == "macos":
        info_path = artifact / "Contents" / "Info.plist"
        if info_path.is_symlink() or not info_path.is_file():
            raise ProtocolError("macOS packaged artifact has no safe Info.plist")
        try:
            info = plistlib.loads(info_path.read_bytes())
        except (OSError, plistlib.InvalidFileException) as exc:
            raise ProtocolError("macOS packaged artifact Info.plist is invalid") from exc
        if info.get("CFBundleIdentifier") != variant["bundle_identity"]:
            raise ProtocolError("macOS packaged artifact bundle identity does not match")
        if require_macos_code_signature:
            _verify_macos_code_signature(artifact)
    _verify_binary_architecture(entrypoint, str(variant["architecture"]))
    return artifact


def _verify_macos_code_signature(artifact: Path) -> None:
    """Require the installed macOS application signature to validate."""

    try:
        result = subprocess.run(
            ["/usr/bin/codesign", "--verify", "--deep", "--strict", str(artifact)],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProtocolError("macOS packaged artifact signature could not be verified") from exc
    if result.returncode != 0:
        raise ProtocolError("macOS packaged artifact signature is invalid")


def _verify_binary_architecture(path: Path, architecture: str) -> None:
    payload = path.read_bytes()[:128]
    actual: str | None = None
    if payload[:4] in {b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf"} and len(payload) >= 8:
        machine = int.from_bytes(
            payload[4:8],
            "little" if payload[:4] == b"\xcf\xfa\xed\xfe" else "big",
        )
        actual = {0x01000007: "x86_64", 0x0100000C: "arm64"}.get(machine)
    elif payload[:2] == b"MZ" and len(payload) >= 70:
        offset = int.from_bytes(payload[60:64], "little")
        if payload[offset : offset + 4] == b"PE\0\0":
            actual = {0x8664: "x86_64", 0xAA64: "arm64"}.get(
                int.from_bytes(payload[offset + 4 : offset + 6], "little")
            )
    elif payload[:4] == b"\x7fELF" and len(payload) >= 20:
        actual = {62: "x86_64", 183: "arm64"}.get(
            int.from_bytes(
                payload[18:20],
                "little" if payload[5:6] == b"\x01" else "big",
            )
        )
    if actual != architecture:
        raise ProtocolError("packaged artifact architecture does not match selection")


__all__ = ["artifact_digest", "verify_platform_artifact"]
