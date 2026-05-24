"""Download, checksum, and safe zip extraction helpers."""

from __future__ import annotations

import hashlib
import shutil
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

MAX_BUNDLE_BYTES = 250 * 1024 * 1024


class DownloadError(RuntimeError):
    """Raised for unsafe downloads or archives."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_sha256(path: Path, expected: str) -> str:
    actual = sha256_file(path)
    if actual.lower() != expected.lower():
        raise DownloadError(f"sha256 mismatch for {path.name}: expected {expected}, got {actual}")
    return actual


def download_to_file(url: str, dest: Path, *, timeout: int = 30, max_bytes: int = MAX_BUNDLE_BYTES) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if url.startswith("file://"):
        src = Path(url.removeprefix("file://"))
        if src.stat().st_size > max_bytes:
            raise DownloadError("bundle is too large")
        shutil.copy2(src, dest)
        return

    request = urllib.request.Request(url, headers={"User-Agent": "rumi-pack-updater/1.0"})
    total = 0
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response, dest.open("wb") as f:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise DownloadError("bundle is too large")
                f.write(chunk)
    except urllib.error.URLError as exc:
        raise DownloadError(f"failed to download {url}: {exc}") from exc


def safe_extract_zip(archive_path: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    dest_resolved = dest.resolve()
    with zipfile.ZipFile(archive_path, "r") as zf:
        for info in zf.infolist():
            name = info.filename
            _validate_zip_entry(info)
            target = dest / name
            try:
                target.resolve().relative_to(dest_resolved)
            except ValueError as exc:
                raise DownloadError(f"archive entry escapes destination: {name!r}") from exc
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)


def validate_zip_entries(archive_path: Path) -> None:
    with zipfile.ZipFile(archive_path, "r") as zf:
        for info in zf.infolist():
            _validate_zip_entry(info)


def _validate_zip_entry(info: zipfile.ZipInfo) -> None:
    name = info.filename
    if name.startswith(("/", "\\")) or "\x00" in name:
        raise DownloadError(f"unsafe archive entry: {name!r}")
    parts = name.replace("\\", "/").split("/")
    if ".." in parts:
        raise DownloadError(f"path traversal in archive entry: {name!r}")
    file_type = (info.external_attr >> 16) & 0o170000
    if file_type == 0o120000:
        raise DownloadError(f"symlink in archive rejected: {name!r}")
