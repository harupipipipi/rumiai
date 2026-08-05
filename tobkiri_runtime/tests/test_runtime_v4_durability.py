"""Cross-platform durability contracts for Profile v4 activation state."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tobkiri_protocol import durability


def _temporary_files(path: Path) -> list[Path]:
    return list(path.glob(".state.json.*.tmp"))


def test_atomic_write_creates_and_replaces_only_after_file_fsync(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "state.json"
    events: list[str] = []
    real_fsync = durability.os.fsync
    real_replace = durability.os.replace

    def fsync(descriptor: int) -> None:
        events.append("file_fsync")
        real_fsync(descriptor)

    def replace(source: Path, destination: Path) -> None:
        events.append("replace")
        real_replace(source, destination)

    monkeypatch.setattr(durability.os, "fsync", fsync)
    monkeypatch.setattr(durability.os, "replace", replace)
    monkeypatch.setattr(
        durability,
        "flush_directory",
        lambda _path: events.append("directory_flush"),
    )

    durability.write_bytes_atomic(target, b"first")
    durability.write_bytes_atomic(target, b"second")

    assert target.read_bytes() == b"second"
    assert events == [
        "file_fsync",
        "replace",
        "directory_flush",
        "file_fsync",
        "replace",
        "directory_flush",
    ]
    assert _temporary_files(tmp_path) == []


def test_atomic_write_failure_before_replace_preserves_target_and_cleans_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "state.json"
    target.write_bytes(b"old")

    def fail_replace(_source: Path, _destination: Path) -> None:
        raise PermissionError("replace denied")

    monkeypatch.setattr(durability.os, "replace", fail_replace)
    with pytest.raises(PermissionError, match="replace denied"):
        durability.write_bytes_atomic(target, b"new")

    assert target.read_bytes() == b"old"
    assert _temporary_files(tmp_path) == []


def test_atomic_write_file_flush_error_preserves_target_and_cleans_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "state.json"
    target.write_bytes(b"old")

    def fail_fsync(_descriptor: int) -> None:
        raise OSError("file flush failed")

    monkeypatch.setattr(durability.os, "fsync", fail_fsync)
    with pytest.raises(OSError, match="file flush failed"):
        durability.write_bytes_atomic(target, b"new")

    assert target.read_bytes() == b"old"
    assert _temporary_files(tmp_path) == []


def test_atomic_write_failure_after_replace_is_reported_and_cleans_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "state.json"
    target.write_bytes(b"old")

    def fail_flush(_path: Path) -> None:
        raise PermissionError("directory flush denied")

    monkeypatch.setattr(durability, "flush_directory", fail_flush)
    with pytest.raises(PermissionError, match="directory flush denied"):
        durability.write_bytes_atomic(target, b"new")

    assert target.read_bytes() == b"new"
    assert _temporary_files(tmp_path) == []


class _WindowsDirectoryApi:
    def __init__(
        self,
        *,
        handle: int | None = 73,
        flush_succeeds: bool = True,
        close_succeeds: bool = True,
    ) -> None:
        self.handle = handle
        self.flush_succeeds = flush_succeeds
        self.close_succeeds = close_succeeds
        self.calls: list[tuple[str, object]] = []

    def CreateFileW(self, *arguments: object) -> int | None:
        self.calls.append(("create", arguments))
        return self.handle

    def FlushFileBuffers(self, handle: int) -> bool:
        self.calls.append(("flush", handle))
        return self.flush_succeeds

    def CloseHandle(self, handle: int) -> bool:
        self.calls.append(("close", handle))
        return self.close_succeeds


def test_windows_directory_flush_uses_backup_semantics_and_closes_handle(
    tmp_path: Path,
) -> None:
    native = _WindowsDirectoryApi()

    durability._flush_windows_directory(tmp_path, kernel32=native)

    create_arguments = native.calls[0][1]
    assert isinstance(create_arguments, tuple)
    assert create_arguments[0] == str(tmp_path)
    assert create_arguments[2] == 0x00000001 | 0x00000002 | 0x00000004
    assert create_arguments[5] == 0x02000000
    assert native.calls[1:] == [("flush", 73), ("close", 73)]


@pytest.mark.parametrize("failure", ["open", "flush", "close"])
def test_windows_directory_flush_propagates_native_errors_and_closes_if_open(
    tmp_path: Path, failure: str
) -> None:
    native = _WindowsDirectoryApi(
        handle=None if failure == "open" else 73,
        flush_succeeds=failure != "flush",
        close_succeeds=failure != "close",
    )

    with pytest.raises(OSError, match="Windows error"):
        durability._flush_windows_directory(tmp_path, kernel32=native)

    call_names = [item[0] for item in native.calls]
    if failure == "open":
        assert call_names == ["create"]
    else:
        assert call_names == ["create", "flush", "close"]


def test_posix_directory_open_error_is_not_silenced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if os.name == "nt":
        pytest.skip("POSIX directory descriptor contract")

    def fail_open(_path: Path, _flags: int) -> int:
        raise PermissionError("directory open denied")

    monkeypatch.setattr(durability.os, "open", fail_open)
    with pytest.raises(PermissionError, match="directory open denied"):
        durability.flush_directory(tmp_path)
